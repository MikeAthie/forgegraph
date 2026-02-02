"""Encryption service for securing sensitive data at rest.

Uses Fernet symmetric encryption from the cryptography library.
Fernet guarantees that a message encrypted using it cannot be
manipulated or read without the key.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""

    pass


class EncryptionService:
    """Service for encrypting and decrypting sensitive data.

    Uses Fernet symmetric encryption. The encryption key must be set
    in Django settings as ENCRYPTION_KEY (a URL-safe base64-encoded 32-byte key).

    Generate a key with:
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """

    _instance: EncryptionService | None = None

    def __init__(self, key: str | None = None):
        """Initialize with encryption key.

        Args:
            key: Fernet key as string. If None, reads from settings.ENCRYPTION_KEY.
        """
        if key is None:
            key = getattr(settings, "ENCRYPTION_KEY", None)
            if not key:
                raise EncryptionError(
                    "ENCRYPTION_KEY not configured in settings. "
                    'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
                )

        try:
            self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError) as e:
            raise EncryptionError(f"Invalid encryption key: {e}") from e

    @classmethod
    def get_instance(cls) -> EncryptionService:
        """Get singleton instance of the encryption service."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a string.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Encrypted bytes (Fernet token).

        Raises:
            EncryptionError: If encryption fails.
        """
        if not plaintext:
            raise EncryptionError("Cannot encrypt empty string")

        try:
            return self.cipher.encrypt(plaintext.encode("utf-8"))
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}") from e

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt bytes back to string.

        Args:
            ciphertext: The encrypted bytes (Fernet token).

        Returns:
            Decrypted string.

        Raises:
            EncryptionError: If decryption fails (invalid token or key).
        """
        if not ciphertext:
            raise EncryptionError("Cannot decrypt empty ciphertext")

        try:
            return self.cipher.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as e:
            raise EncryptionError("Decryption failed: invalid token or key mismatch") from e
        except Exception as e:
            raise EncryptionError(f"Decryption failed: {e}") from e


def encrypt_api_key(api_key: str) -> bytes:
    """Convenience function to encrypt an API key.

    Args:
        api_key: The API key to encrypt.

    Returns:
        Encrypted bytes.
    """
    return EncryptionService.get_instance().encrypt(api_key)


def decrypt_api_key(encrypted_key: bytes) -> str:
    """Convenience function to decrypt an API key.

    Args:
        encrypted_key: The encrypted API key bytes.

    Returns:
        Decrypted API key string.
    """
    return EncryptionService.get_instance().decrypt(encrypted_key)
