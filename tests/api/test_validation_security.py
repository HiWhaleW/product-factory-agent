from app.domain.schemas import ProviderCredentialUpdate
from app.main import redact_validation_errors
from pydantic import ValidationError


def test_api_key_is_redacted_from_validation_errors() -> None:
    leaked_value = "zxq91"
    try:
        ProviderCredentialUpdate(
            provider_name="测试接口",
            base_url="https://models.example.com/v1",
            model_name="test-model",
            api_key=leaked_value,
        )
    except ValidationError as error:
        fields = redact_validation_errors(error.errors(include_url=False))
    else:
        raise AssertionError("invalid key unexpectedly passed validation")

    assert fields[0]["input"] == "[REDACTED]"
    assert leaked_value not in repr(fields)
