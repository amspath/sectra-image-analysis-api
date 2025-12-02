

from io import BytesIO

from PIL import Image


class JPEGImage:
    """Model for JPEG images."""
    image: bytes

    def convert_to_pil(self) -> Image:
        """Converts the JPEG image bytes to a PIL Image object.

        Returns:
            Image: PIL Image object
        """
        return Image.open(BytesIO(self.image))