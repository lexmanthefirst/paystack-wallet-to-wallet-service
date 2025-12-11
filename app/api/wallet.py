import json
from datetime import timedelta
from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import User
from app.schemas.wallet import DepositRequest, TransferRequest
from app.services import wallet as wallet_service
from app.services import transaction as transaction_service
from app.services.paystack import paystack_service
from app.api.deps import get_current_user, require_permissions
from app.utils.responses import success_response, fail_response
from app.utils.rate_limit import rate_limit

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.post("/deposit")
@rate_limit(max_requests=5, window=timedelta(minutes=1))
async def deposit_to_wallet(
    request: Request,
    deposit_data: DepositRequest,
    current_user: User = Depends(require_permissions(["deposit"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Initialize a deposit to wallet using Paystack.
    
    Requires JWT or API key with 'deposit' permission.
    """
    # Get user's wallet
    wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    
    if not wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Wallet not found"
        )
    
    # Use service to initialize deposit
    try:
        from app.services.deposit import initialize_deposit
        
        deposit_result = await initialize_deposit(
            db=db,
            wallet=wallet,
            amount=deposit_data.amount,
            user_email=current_user.email
        )
        
        return success_response(
            status_code=status.HTTP_200_OK,
            message="Deposit initialized successfully",
            data=deposit_result
        )
        
    except Exception as e:
        return fail_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to initialize payment: {str(e)}"
        )


@router.get("/payment/callback", summary="Payment Callback")
async def deposit_callback(request: Request):
    """Handle Paystack redirect after payment."""
    reference = request.query_params.get("reference") or request.query_params.get("trxref")
    if not reference:
        return success_response(
            status_code=status.HTTP_200_OK,
            message="Payment processing",
            data={"status": "processing"}
        )
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Payment received. Check your wallet balance or transaction history.",
        data={
            "reference": reference,
            "status": "completed",
            "note": "Funds will be credited within seconds via webhook"
        }
    )



@router.get(
    "/deposit/{reference}/status",
    summary="Get Deposit Status",
    description="""
    Check the status of a deposit transaction without crediting the wallet.
    
    **Purpose:** Read-only status check for manual verification.
    
    **Important:** This endpoint does NOT credit wallets. 
    Only the Paystack webhook is allowed to credit wallets.
    
    **Use Cases:**
    - Manual verification of deposit status
    - Debugging payment issues
    - User status inquiry
    
    **Authentication:** Requires JWT or API key with 'read' permission
    """,
    responses={
        200: {
            "description": "Deposit status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Deposit status retrieved",
                        "data": {
                            "reference": "DEP_ABC123XYZ",
                            "status": "success",
                            "amount": "5000.00"
                        }
                    }
                }
            }
        },
        404: {
            "description": "Transaction not found or not owned by user",
            "content": {
                "application/json": {
                    "example": {
                        "status": "fail",
                        "message": "Transaction not found"
                    }
                }
            }
        }
    }
)
async def get_deposit_status(
    reference: str,
    current_user: User = Depends(require_permissions(["read"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Get deposit transaction status (read-only, does NOT credit wallet).
    
    Requires JWT or API key with 'read' permission.
    """
    # Get transaction by reference
    transaction = await transaction_service.get_transaction_by_reference(db, reference)
    
    if not transaction:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Transaction not found"
        )
    
    # Verify transaction belongs to the current user
    wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    if not wallet or transaction.wallet_id != wallet.id:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Transaction not found"
        )
    
    # Return status (read-only, no wallet crediting)
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Deposit status retrieved",
        data={
            "reference": transaction.reference,
            "status": transaction.status.value,
            "amount": str(transaction.amount)
        }
    )


@router.post("/paystack/webhook")
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Paystack webhook for payment notifications.
    
    This endpoint validates the webhook signature and credits the wallet.
    """
    # Get request body and signature
    body = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    
    # Validate signature
    if not paystack_service.validate_webhook_signature(body, signature):
        return fail_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Invalid webhook signature"
        )
    
    # Parse webhook data
    data = json.loads(body)
    
    # Timestamp validation (replay attack prevention)
    from datetime import datetime, timezone, timedelta
    event_data = data.get("data", {})
    created_at = event_data.get("created_at") or event_data.get("createdAt")
    
    if created_at:
        try:
            # Parse ISO format timestamp (Paystack uses ISO 8601)
            webhook_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            age = datetime.now(timezone.utc) - webhook_time
            
            # Reject webhooks older than 5 minutes
            if age > timedelta(minutes=5):
                from app.utils.logger import logger
                logger.warning(
                    f"Webhook rejected - too old: {age.total_seconds()}s",
                    extra={"age_seconds": age.total_seconds(), "created_at": created_at}
                )
                return fail_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    message="Webhook expired"
                )
        except (ValueError, TypeError) as e:
            # Log but don't reject - timestamp might be in unexpected format
            from app.utils.logger import logger
            logger.warning(f"Could not parse webhook timestamp: {created_at}", exc_info=True)
    
    event = data.get("event")
    
    # Handle charge.success event
    if event == "charge.success":
        reference = event_data.get("reference")
        
        if not reference:
            return fail_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Missing transaction reference"
            )
        
        # Use webhook service to process the charge
        try:
            from app.services.webhook import process_successful_charge
            
            result = await process_successful_charge(db=db, reference=reference)
            
            return success_response(
                status_code=status.HTTP_200_OK,
                message=result.get("message", "Webhook processed successfully"),
                data={"status": result.get("status", True)}
            )
            
        except ValueError as e:
            return fail_response(
                status_code=status.HTTP_404_NOT_FOUND,
                message=str(e)
            )
        except Exception as e:
            return fail_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"Error processing webhook: {str(e)}"
            )
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Webhook received",
        data={"status": True}
    )


@router.get("/deposit/{reference}/status")
async def check_deposit_status(
    reference: str,
    current_user: User = Depends(require_permissions(["read"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Check the status of a deposit transaction (read-only).
    
    Requires JWT or API key with 'read' permission.
    """
    transaction = await transaction_service.get_transaction_by_reference(db, reference)
    
    if not transaction:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Transaction not found"
        )
    
    # Verify transaction belongs to current user
    wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    
    if not wallet or transaction.wallet_id != wallet.id:
        return fail_response(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Transaction does not belong to current user"
        )
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Deposit status retrieved successfully",
        data={
            "reference": transaction.reference,
            "status": transaction.status.value,
            "amount": str(transaction.amount)
        }
    )


@router.get("/balance")
async def get_wallet_balance(
    current_user: User = Depends(require_permissions(["read"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Get wallet balance.
    
    Requires JWT or API key with 'read' permission.
    """
    wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    
    if not wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Wallet not found"
        )
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Balance retrieved successfully",
        data={
            "wallet_number": wallet.wallet_number,
            "balance": str(wallet.balance)
        }
    )


@router.post("/transfer")
async def transfer_funds(
    transfer_data: TransferRequest,
    current_user: User = Depends(require_permissions(["transfer"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Transfer funds to another wallet.
    
    Requires JWT or API key with 'transfer' permission.
    """
    # Get sender wallet
    sender_wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    
    if not sender_wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Sender wallet not found"
        )
    
    # Get recipient wallet
    recipient_wallet = await wallet_service.get_wallet_by_number(db, transfer_data.wallet_number)
    
    if not recipient_wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Recipient wallet not found"
        )
    
    # Perform transfer
    try:
        if sender_wallet.id == recipient_wallet.id:
            return fail_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Cannot transfer to your own wallet"
            )

        # Call the concurrency-safe transfer service
        await wallet_service.transfer_funds(
            db=db,
            sender_wallet_number=sender_wallet.wallet_number,
            recipient_wallet_number=recipient_wallet.wallet_number,
            amount=transfer_data.amount
        )
        
        return success_response(
            status_code=status.HTTP_200_OK,
            message="Transfer completed successfully",
            data={
                "status": "success",
                "amount": str(transfer_data.amount),
                "recipient_wallet": transfer_data.wallet_number
            }
        )
        
    except ValueError as e:
        return fail_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(e)
        )
    except Exception as e:
         return fail_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Transfer failed: {str(e)}"
        )


@router.get("/transactions")
async def get_transaction_history(
    current_user: User = Depends(require_permissions(["read"])),
    db: AsyncSession = Depends(get_db)
):
    """
    Get transaction history.
    
    Requires JWT or API key with 'read' permission.
    """
    wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    
    if not wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Wallet not found"
        )
    
    transactions = await wallet_service.get_wallet_transactions(db, str(wallet.id))
    
    # Format transactions for response
    transactions_data = [
        {
            "id": str(txn.id),
            "type": txn.type.value,
            "amount": str(txn.amount),
            "reference": txn.reference,
            "status": txn.status.value,
            "created_at": txn.created_at.isoformat()
        }
        for txn in transactions
    ]
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Transaction history retrieved successfully",
        data={"transactions": transactions_data}
    )
