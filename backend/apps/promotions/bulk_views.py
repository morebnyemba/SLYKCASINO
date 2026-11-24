"""Admin API for bulk bonus grants (promotions.bulk). Superusers only: these move money for every player."""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import bulk
from .models import BulkGrant


class _Superuser(APIView):
    permission_classes = [IsAdminUser]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only a superuser can give or take bonuses in bulk.')


class AdminBulkGrantsView(_Superuser):
    """GET: recent grants · POST {preview?, kind, audience, amount, wagering_multiplier, name, message, confirm_total}."""

    def get(self, request):
        return Response({'results': [bulk.payload(g) for g in BulkGrant.objects.select_related('undo_of')[:30]],
                         'audiences': BulkGrant.Audience.choices, 'max_per_player': f'{bulk.MAX_PER_PLAYER:.2f}'})

    def post(self, request):
        d = request.data
        try:
            numbers = bulk.preview(kind=str(d.get('kind') or ''), audience=str(d.get('audience') or ''), amount=d.get('amount'))
            if d.get('preview'):
                return Response(numbers)
            # The person must type back the total they saw: a typo in the amount can't go out to everyone.
            if str(d.get('confirm_total') or '').strip().lstrip('$') != numbers['total']:
                return Response({'detail': f'Type the total exactly as shown (${numbers["total"]}) to confirm.'},
                                status=status.HTTP_400_BAD_REQUEST)
            grant = bulk.start(kind=d.get('kind'), audience=d.get('audience'), amount=d.get('amount'),
                               wagering=d.get('wagering_multiplier'), name=str(d.get('name') or ''),
                               message=str(d.get('message') or ''), by=request.user.get_username())
        except bulk.BulkError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(bulk.payload(grant), status=status.HTTP_201_CREATED)


class AdminBulkGrantView(_Superuser):
    """GET one grant · POST {action: 'undo' | 'resume'}."""

    def get(self, request, pk: int):
        grant = BulkGrant.objects.filter(pk=pk).first()
        if grant is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(bulk.payload(grant))

    def post(self, request, pk: int):
        grant = BulkGrant.objects.filter(pk=pk).first()
        if grant is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        act = request.data.get('action')
        try:
            if act == 'undo':
                return Response(bulk.payload(bulk.undo(grant, by=request.user.get_username())), status=status.HTTP_201_CREATED)
            if act == 'resume':
                if not bulk.stalled(grant) and grant.status != BulkGrant.Status.FAILED:
                    raise bulk.BulkError('This grant is not stuck.')
                BulkGrant.objects.filter(pk=pk).update(status=BulkGrant.Status.RUNNING, error='')
                from apps.accounts import services as accounts
                accounts.audit(None, 'bulk_grant_resumed', request, grant=pk)
                bulk.enqueue(pk)
                return Response(bulk.payload(BulkGrant.objects.get(pk=pk)))
        except bulk.BulkError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Unknown action.'}, status=status.HTTP_400_BAD_REQUEST)
