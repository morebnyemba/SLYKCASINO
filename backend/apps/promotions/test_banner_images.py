"""Banner images: `?w=` serves a smaller WebP of a still image; everything else is untouched."""
from __future__ import annotations

import io

from django.core.cache import cache
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from apps.promotions.models import BannerImage


def picture(fmt='JPEG', size=(1920, 1280), frames=1) -> bytes:
    buf = io.BytesIO()
    imgs = [Image.new('RGB', size, (200, 30 + i * 40, 60)) for i in range(frames)]
    if frames > 1:
        imgs[0].save(buf, fmt, save_all=True, append_images=imgs[1:], duration=100, loop=0)
    else:
        imgs[0].save(buf, fmt, quality=95)
    return buf.getvalue()


class BannerImageResizeTests(TestCase):
    def setUp(self):
        cache.clear()

    def store(self, data, content_type):
        return BannerImage.objects.create(content=data, content_type=content_type, size=len(data))

    def get(self, pk, query=''):
        return APIClient().get(f'/api/promotions/banner-images/{pk}/{query}')

    def test_width_returns_a_smaller_webp(self):
        img = self.store(picture(), 'image/jpeg')
        res = self.get(img.pk, '?w=828')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'image/webp')
        self.assertIn('immutable', res['Cache-Control'])
        body = b''.join(res.streaming_content) if res.streaming else res.content
        with Image.open(io.BytesIO(body)) as out:
            self.assertEqual(out.size, (828, 552))
        self.assertLess(len(body), img.size)

    def test_original_without_width_or_with_an_unlisted_one(self):
        img = self.store(picture(), 'image/jpeg')
        for q in ('', '?w=777', '?w=abc'):
            res = self.get(img.pk, q)
            self.assertEqual(res['Content-Type'], 'image/jpeg', q)
            self.assertEqual(len(res.content), img.size, q)

    def test_animated_gif_and_small_images_are_left_alone(self):
        gif = self.store(picture('GIF', (1200, 400), frames=3), 'image/gif')
        self.assertEqual(self.get(gif.pk, '?w=480')['Content-Type'], 'image/gif')
        small = self.store(picture(size=(400, 200)), 'image/jpeg')
        self.assertEqual(self.get(small.pk, '?w=828')['Content-Type'], 'image/jpeg')

    def test_png_with_transparency_keeps_alpha(self):
        buf = io.BytesIO()
        Image.new('RGBA', (1600, 500), (255, 0, 0, 120)).save(buf, 'PNG')
        img = self.store(buf.getvalue(), 'image/png')
        res = self.get(img.pk, '?w=480')
        with Image.open(io.BytesIO(res.content)) as out:
            self.assertEqual(out.mode, 'RGBA')
