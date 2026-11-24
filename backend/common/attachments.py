"""Images and videos staff send to players (WhatsApp inbox, support chat).

The type is read from the file's first bytes, never trusted from its name or
the browser, and the sizes are WhatsApp's own limits so one rule fits both:
JPG/PNG up to 5 MB, MP4/3GP (H.264 video) up to 16 MB.
"""
from __future__ import annotations

from dataclasses import dataclass

IMAGE_MAX = 5 * 1024 * 1024
VIDEO_MAX = 16 * 1024 * 1024


class AttachmentError(ValueError):
    """Why a file can't be sent (shown to staff)."""


@dataclass(frozen=True)
class Attachment:
    kind: str        # 'image' | 'video'
    mime: str
    ext: str


def sniff(head: bytes) -> Attachment | None:
    if head.startswith(b'\xff\xd8\xff'):
        return Attachment('image', 'image/jpeg', 'jpg')
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return Attachment('image', 'image/png', 'png')
    if head[4:8] == b'ftyp':
        brand = head[8:12]
        if brand.startswith(b'3g'):
            return Attachment('video', 'video/3gpp', '3gp')
        if brand == b'qt  ':
            return None                                 # QuickTime (.mov): WhatsApp refuses it
        return Attachment('video', 'video/mp4', 'mp4')
    return None


def inspect(upload) -> Attachment:
    """Check an uploaded file and say what it is, or AttachmentError."""
    if upload is None:
        raise AttachmentError('Choose a photo or video.')
    head = upload.read(16)
    upload.seek(0)
    found = sniff(head)
    if found is None:
        raise AttachmentError('Send a JPG or PNG photo, or an MP4 video (an iPhone .mov must be converted to MP4 first).')
    limit = IMAGE_MAX if found.kind == 'image' else VIDEO_MAX
    if upload.size > limit:
        raise AttachmentError(f'{"Photos" if found.kind == "image" else "Videos"} can be at most {limit // (1024 * 1024)} MB.')
    return found
