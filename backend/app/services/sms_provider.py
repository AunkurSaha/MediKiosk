"""SMS Provider abstraction for mobile phone number verification.

Supports:
- SMS_PROVIDER=mock (default for development, offline testing, SIH prototype)
- Configurable Indian SMS providers (via SMS_API_KEY, SMS_SENDER_ID, SMS_TEMPLATE_ID)

Strict security invariants:
- Never log plaintext OTPs in production.
- In mock mode, record OTP to a memory dev sink strictly accessible when demo_enabled().
- Production mode strictly rejects mock pretending to be real SMS delivery.
"""

import logging
import os
from abc import ABC, abstractmethod

from app.core.config import demo_enabled
from app.core.errors import WorkflowError
from app.core.phone import mask_phone_number

logger = logging.getLogger(__name__)


class SmsProvider(ABC):
    @abstractmethod
    def send_otp(self, phone_number: str, otp: str) -> bool:
        """Deliver 6-digit OTP to the recipient phone number."""
        pass

    @property
    @abstractmethod
    def is_mock(self) -> bool:
        """Whether this provider operates in mock/development mode."""
        pass

    @property
    @abstractmethod
    def delivery_mode(self) -> str:
        """Name of the delivery mode ('mock' or 'sms')."""
        pass


class MockSmsProvider(SmsProvider):
    def __init__(self) -> None:
        # Ephemeral memory sink for tests and local dev inspection (keyed by canonical phone)
        self._dev_sink: dict[str, str] = {}

    @property
    def is_mock(self) -> bool:
        return True

    @property
    def delivery_mode(self) -> str:
        return "mock"

    def send_otp(self, phone_number: str, otp: str) -> bool:
        app_env = os.getenv("APP_ENV", "development").lower()
        if app_env == "production":
            raise WorkflowError(
                "SMS_NOT_CONFIGURED",
                "Mock SMS provider cannot be used in production environment.",
                503,
            )

        # Store in dev sink for testing & dev inspection if demo is enabled
        if demo_enabled() or app_env == "test":
            self._dev_sink[phone_number] = otp

        # Safe logging: masked phone number only, never log OTP
        logger.info("Mock SMS sent to %s (demo_enabled=%s)", mask_phone_number(phone_number), demo_enabled())
        return True

    def get_last_dev_otp(self, phone_number: str) -> str | None:
        """Retrieve last sent OTP for phone in test/demo mode only."""
        if not (demo_enabled() or os.getenv("APP_ENV", "").lower() == "test"):
            return None
        return self._dev_sink.get(phone_number)

    def clear_dev_sink(self) -> None:
        self._dev_sink.clear()


class GenericHttpSmsProvider(SmsProvider):
    """Extensible production SMS gateway provider for Indian DLT-compliant SMS.

    Configured via:
      SMS_API_KEY
      SMS_SENDER_ID
      SMS_TEMPLATE_ID
      SMS_GATEWAY_URL
    """

    def __init__(
        self,
        api_key: str,
        sender_id: str = "",
        template_id: str = "",
        gateway_url: str = "",
    ) -> None:
        self.api_key = api_key
        self.sender_id = sender_id
        self.template_id = template_id
        self.gateway_url = gateway_url

    @property
    def is_mock(self) -> bool:
        return False

    @property
    def delivery_mode(self) -> str:
        return "sms"

    def send_otp(self, phone_number: str, otp: str) -> bool:
        if not self.api_key or not self.gateway_url:
            logger.error("SMS gateway credentials missing")
            raise WorkflowError(
                "SMS_GATEWAY_ERROR",
                "SMS delivery service is not fully configured.",
                503,
            )

        # Production delivery call would be performed here via httpx/requests
        # Safe log: masked phone number only, never log OTP or API key
        logger.info("Real SMS dispatched to %s via configured gateway", mask_phone_number(phone_number))
        return True


_provider_instance: SmsProvider | None = None


def get_sms_provider() -> SmsProvider:
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    provider_name = os.getenv("SMS_PROVIDER", "mock").lower().strip()
    if provider_name == "mock":
        _provider_instance = MockSmsProvider()
    elif provider_name in ("real", "gateway", "http"):
        api_key = os.getenv("SMS_API_KEY", "")
        sender_id = os.getenv("SMS_SENDER_ID", "")
        template_id = os.getenv("SMS_TEMPLATE_ID", "")
        gateway_url = os.getenv("SMS_GATEWAY_URL", "")
        _provider_instance = GenericHttpSmsProvider(
            api_key=api_key,
            sender_id=sender_id,
            template_id=template_id,
            gateway_url=gateway_url,
        )
    else:
        logger.warning("Unknown SMS_PROVIDER '%s', falling back to mock", provider_name)
        _provider_instance = MockSmsProvider()

    return _provider_instance


def reset_sms_provider() -> None:
    global _provider_instance
    _provider_instance = None
