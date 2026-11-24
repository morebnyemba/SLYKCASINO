import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from common.attachments import IMAGE_MAX, inspect, AttachmentError

JPG = b'\xff\xd8\xff\xe0' + b'0' * 200
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 200
MP4 = b'\x00\x00\x00\x18ftypmp42' + b'0' * 200
MOV = b'\x00\x00\x00\x14ftypqt  ' + b'0' * 200
GIF = b'GIF89a' + b'0' * 200
MEDIA = tempfile.mkdtemp()


def upload(data, name='x.bin', ctype='application/octet-stream'):
    return SimpleUploadedFile(name, data, content_type=ctype)


class _Res:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.text = status, body or {}, ''

    def json(self):
        return self._body


class SniffTests(TestCase):
    def test_type_comes_from_the_bytes_not_the_name(self):
        self.assertEqual(inspect(upload(JPG, 'evil.exe')).mime, 'image/jpeg')
        self.assertEqual(inspect(upload(PNG)).kind, 'image')
        self.assertEqual(inspect(upload(MP4, 'clip.jpg')).mime, 'video/mp4')
        for bad in (GIF, MOV, b'<script>'):
            with self.assertRaises(AttachmentError):
                inspect(upload(bad, 'photo.jpg', 'image/jpeg'))
        with self.assertRaises(AttachmentError):
            inspect(upload(JPG + b'0' * IMAGE_MAX))


@override_settings(MEDIA_ROOT=MEDIA)
class SupportAttachmentTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.p = accounts.register_player(username='rudo', email='r@example.com', password='Pass-word-123')
        self.other = accounts.register_player(username='tari', email='t@example.com', password='Pass-word-123')
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('desk', 'd@example.com', 'x', is_staff=True))

    def as_player(self, player):
        c = APIClient()
        c.force_authenticate(player.user)
        return c

    def test_staff_send_a_photo_the_player_sees_it_nobody_else_does(self):
        res = self.staff.post(f'/api/admin/support/{self.p.id}/', {'file': upload(JPG, 'promo.jpg'), 'body': ''}, format='multipart')
        self.assertEqual(res.status_code, 201, res.content)
        att = res.json()['attachment']
        self.assertEqual(att['kind'], 'image')
        mine = self.as_player(self.p).get('/api/support/messages/').json()
        msgs = mine.get('results', mine) if isinstance(mine, dict) else mine
        self.assertTrue(any(m.get('attachment') for m in msgs))
        got = self.as_player(self.p).get(att['url'])
        self.assertEqual((got.status_code, got['Content-Type']), (200, 'image/jpeg'))
        self.assertEqual(b''.join(got.streaming_content), JPG)
        self.assertEqual(self.as_player(self.other).get(att['url']).status_code, 404)
        self.assertEqual(APIClient().get(att['url']).status_code, 404)
        self.assertEqual(self.staff.get(att['url']).status_code, 200)

    def test_a_video_with_a_message_and_bad_files_refused(self):
        res = self.staff.post(f'/api/admin/support/{self.p.id}/', {'file': upload(MP4), 'body': 'Watch this'}, format='multipart')
        self.assertEqual((res.json()['attachment']['kind'], res.json()['body']), ('video', 'Watch this'))
        bad = self.staff.post(f'/api/admin/support/{self.p.id}/', {'file': upload(GIF, 'a.gif')}, format='multipart')
        self.assertEqual(bad.status_code, 400)
        self.assertIn('JPG or PNG', bad.json()['detail'])
        self.assertEqual(self.staff.post(f'/api/admin/support/{self.p.id}/', {'body': ''}, format='json').status_code, 400)


@override_settings(MEDIA_ROOT=MEDIA, WHATSAPP_TOKEN='tok', WHATSAPP_PHONE_NUMBER_ID='555')
class WhatsAppMediaTests(TestCase):
    def setUp(self):
        from apps.chatbot.models import InboundMessage
        self.number = '263771234567'
        InboundMessage.objects.create(provider_id='w.1', address=self.number, text='hi')
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('desk', 'd@example.com', 'x', is_staff=True))

    def test_staff_send_a_video_uploaded_to_meta_then_sent_with_its_caption(self):
        from apps.chatbot.models import OutboundMessage
        calls = [_Res(200, {'id': 'MEDIA1'}), _Res(200, {'messages': [{'id': 'wamid.V'}]})]
        with patch('requests.post', side_effect=calls) as post:
            res = self.staff.post(f'/api/admin/chatbot/inbox/{self.number}/', {'file': upload(MP4, 'promo.mp4'), 'text': 'Big match tonight'},
                                  format='multipart')
        self.assertEqual(res.status_code, 201, res.content)
        up, send = post.call_args_list
        self.assertTrue(up.args[0].endswith('/555/media'))
        self.assertEqual(up.kwargs['data'], {'messaging_product': 'whatsapp', 'type': 'video/mp4'})
        self.assertEqual(up.kwargs['files']['file'][1], MP4)
        self.assertEqual(send.kwargs['json']['type'], 'video')
        self.assertEqual(send.kwargs['json']['video'], {'id': 'MEDIA1', 'caption': 'Big match tonight'})
        row = OutboundMessage.objects.get()
        self.assertEqual((row.status, row.media_kind, row.provider_id), ('sent', 'video', 'wamid.V'))
        shown = next(m for m in res.json()['messages'] if m['direction'] == 'out')
        self.assertEqual(shown['media']['kind'], 'video')
        self.assertEqual(self.staff.get(shown['media']['url']).status_code, 200)

    def test_meta_refusing_the_file_is_reported(self):
        from apps.chatbot.models import OutboundMessage
        with patch('requests.post', return_value=_Res(400, {'error': {'code': 131053, 'message': 'Media upload error'}})):
            self.staff.post(f'/api/admin/chatbot/inbox/{self.number}/', {'file': upload(JPG)}, format='multipart')
        row = OutboundMessage.objects.get()
        self.assertEqual(row.status, 'failed')
        self.assertIn('Meta refused the file', row.error)

    def test_outside_the_24_hour_window_nothing_is_sent(self):
        from apps.chatbot.models import InboundMessage
        InboundMessage.objects.filter(address=self.number).update(received_at=timezone.now() - timezone.timedelta(days=2))
        with patch('requests.post') as post:
            res = self.staff.post(f'/api/admin/chatbot/inbox/{self.number}/', {'file': upload(JPG)}, format='multipart')
        self.assertEqual(res.status_code, 400)
        post.assert_not_called()
