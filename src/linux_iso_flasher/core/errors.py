"""Hierarquia de erros da aplicação.

Todos os erros esperados (usuário, dispositivo, permissão, verificação) derivam
de ``FlasherError`` para que a interface possa apresentar mensagens seguras e
traduzidas, sem expor detalhes internos ou sleep de exceções brutas.
"""

from __future__ import annotations


class FlasherError(Exception):
    """Base para erros tratáveis pela interface."""

    message = "Erro desconhecido."

    def __init__(self, message: str | None = None, **details: object) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details: dict[str, object] = details

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class ImageError(FlasherError):
    """Arquivo de imagem inválido, ilegível ou corrompido."""

    message = "Não foi possível utilizar esta imagem."


class UnsupportedFormatError(ImageError):
    message = "Formato de imagem não suportado."


class ImageNotFoundError(ImageError):
    message = "Arquivo de imagem não encontrado."


class ImageTooLargeError(ImageError):
    message = "A imagem é maior que a capacidade do dispositivo."


class DeviceError(FlasherError):
    """Falha ao inspecionar ou acessar o dispositivo de destino."""

    message = "Não foi possível acessar o dispositivo selecionado."


class DeviceNotFoundError(DeviceError):
    message = "O dispositivo selecionado não está mais conectado."


class UnsafeDeviceError(DeviceError):
    message = "Este dispositivo é interno ou não é seguro para gravação."


class DeviceChangedError(DeviceError):
    message = "O dispositivo mudou desde a seleção. Selecione-o novamente."


class PermissionErrorFlasher(FlasherError):
    message = "Permissão administrativa não concedida."


class HelperError(FlasherError):
    message = "O mecanismo privilegiado de gravação falhou."


class WriteError(FlasherError):
    message = "Falha ao gravar a imagem no dispositivo."


class VerificationError(FlasherError):
    message = "A verificação falhou: os dados gravados não conferem com a imagem."


class CancelledError(FlasherError):
    message = "Operação cancelada pelo usuário."
