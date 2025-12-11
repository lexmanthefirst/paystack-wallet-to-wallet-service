from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):    
    # Database
    DATABASE_URL: str
    
    # JWT Configuration
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    
    # Paystack
    PAYSTACK_SECRET_KEY: str
    PAYSTACK_PUBLIC_KEY: str
    
    # Application
    APP_NAME: str = "Wallet Service"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    APP_BASE_URL: str = "https://pleasing-tranquility-production.up.railway.app"
    CORS_ALLOWED_ORIGINS: str = "https://pleasing-tranquility-production.up.railway.app"
    
    # Redis Configuration
    REDIS_URL: str 
    REDIS_ENABLED: bool = True
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
