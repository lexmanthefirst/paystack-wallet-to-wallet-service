import json
from datetime import timedelta
from fastapi import APIRouter, Depends, status, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import User
from app.schemas.wallet import (
    DepositRequest, TransferRequest,
    BalanceSuccessResponse, DepositSuccessResponse, 
    TransferSuccessResponse, TransactionsSuccessResponse
)
from app.services import wallet as wallet_service
from app.services import transaction as transaction_service
from app.services.paystack import paystack_service
from app.services.deposit import initialize_deposit
from app.api.deps import get_current_user, require_permissions
from app.utils.responses import success_response, fail_response
from app.utils.rate_limit import rate_limit
from app.utils.logger import logger

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.post("/deposit", response_model=DepositSuccessResponse)
@rate_limit(max_requests=5, window=timedelta(minutes=1))
async def deposit_to_wallet(
    request: Request,
    deposit_data: DepositRequest,
    current_user: User = Depends(require_permissions(["deposit"])),
    db: AsyncSession = Depends(get_db)
):
    """Initialize Paystack deposit. Requires 'deposit' permission."""
    wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    if not wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Wallet not found"
        )
    
    try:
        deposit_result = await initialize_deposit(
            db=db, wallet=wallet, 
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


@router.get("/payment/callback", include_in_schema=False)
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
        message="Payment received. Check wallet balance or transaction history.",
        data={
        "reference": reference,
        "status": "completed",
        "note": "Funds will be credited within seconds via webhook"
    })



@router.get("/deposit/{reference}/status")
async def get_deposit_status(
    reference: str,
    current_user: User = Depends(require_permissions(["read"])),
    db: AsyncSession = Depends(get_db)
):
    """Get deposit status (read-only, does NOT credit wallet). Requires 'read' permission."""
    transaction = await transaction_service.get_transaction_by_reference(db, reference)
    if not transaction:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Transaction not found"
        )
    
    wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    if not wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Wallet not found"
        )
    
    if transaction.wallet_id != wallet.id:
        return fail_response(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Transaction not found or permission denied"
        )
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Deposit status retrieved",
        data={
        "reference": transaction.reference,
        "status": transaction.status.value,
        "amount": str(transaction.amount)
    })


@router.post("/paystack/webhook", include_in_schema=False)
async def paystack_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Paystack webhook for payment notifications."""
    body = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    
    if not paystack_service.validate_webhook_signature(body, signature):
        return fail_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Invalid webhook signature"
        )
    
    data = json.loads(body)
    
    # Timestamp validation (replay attack prevention)
    from datetime import datetime, timezone, timedelta
    event_data = data.get("data", {})
    created_at = event_data.get("created_at") or event_data.get("createdAt")
    
    if created_at:
        try:
            webhook_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            age = datetime.now(timezone.utc) - webhook_time
            
            if age > timedelta(minutes=5):
                logger.warning(f"Webhook rejected - too old: {age.total_seconds()}s", extra={"age_seconds": age.total_seconds(), "created_at": created_at})
                return fail_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    message="Webhook expired"
                )
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse webhook timestamp: {created_at}", exc_info=True)
    
    event = data.get("event")
    
    if event == "charge.success":
        reference = event_data.get("reference")
        if not reference:
            return fail_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Missing transaction reference"
            )
        
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
    
    elif event == "charge.failed":
        reference = event_data.get("reference")
        if not reference:
            return fail_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Missing transaction reference"
            )
        
        try:
            from app.services.webhook import process_failed_charge
            result = await process_failed_charge(db=db, reference=reference)
            return success_response(
                status_code=status.HTTP_200_OK,
                message=result.get("message", "Failed charge processed"),
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
                message=f"Error processing failed charge: {str(e)}"
            )
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Webhook received",
        data={"status": True}
    )





@router.get("/balance", response_model=BalanceSuccessResponse)
async def get_wallet_balance(
    current_user: User = Depends(require_permissions(["read"])),
    db: AsyncSession = Depends(get_db)
):
    """Get wallet balance. Requires 'read' permission."""
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
    })


@router.post("/transfer", response_model=TransferSuccessResponse)
async def transfer_funds(
    transfer_data: TransferRequest,
    current_user: User = Depends(require_permissions(["transfer"])),
    db: AsyncSession = Depends(get_db)
):
    """Transfer funds to another wallet. Requires 'transfer' permission."""
    sender_wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    if not sender_wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Sender wallet not found"
        )
    
    recipient_wallet = await wallet_service.get_wallet_by_number(db, transfer_data.wallet_number)
    if not recipient_wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Recipient wallet not found"
        )
    
    try:
        if sender_wallet.id == recipient_wallet.id:
            return fail_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Cannot transfer to your own wallet"
            )
        
        await wallet_service.transfer_funds(
            db=db, sender_wallet_number=sender_wallet.wallet_number,
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
        })
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


@router.get("/transactions", response_model=TransactionsSuccessResponse)
async def get_transaction_history(
    limit: int = 50,
    current_user: User = Depends(require_permissions(["read"])),
    db: AsyncSession = Depends(get_db)
):
    """Get transaction history (max 50). Requires 'read' permission."""
    wallet = await wallet_service.get_user_wallet(db, str(current_user.id))
    if not wallet:
        return fail_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Wallet not found"
        )
    
    transactions = await wallet_service.get_wallet_transactions(db, str(wallet.id), limit=limit)
    
    transactions_data = [{
        "id": str(txn.id),
        "type": txn.type.value,
        "amount": str(txn.amount),
        "reference": txn.reference,
        "status": txn.status.value,
        "created_at": txn.created_at.isoformat()
    } for txn in transactions]
    
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Transaction history retrieved successfully",
        data={
        "transactions": transactions_data, 
        "count": len(transactions_data)
    })

