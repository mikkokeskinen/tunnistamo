from collections import OrderedDict
import django
from oidc_provider import settings
from django.contrib.auth import BACKEND_SESSION_KEY
from django.contrib.auth import logout as django_user_logout
from users.models import LoginMethod, OidcClientOptions
from django.contrib.auth.views import redirect_to_login


def combine_uniquely(iterable1, iterable2):
    """
    Combine unique items of two sequences preserving order.

    :type seq1: Iterable[Any]
    :type seq2: Iterable[Any]
    :rtype: list[Any]
    """
    result = OrderedDict.fromkeys(iterable1)
    for item in iterable2:
        result[item] = None
    return list(result.keys())


def after_userlogin_hook(request, user, client):
    """Marks Django session modified

    The purpose of this function is to keep the session used by the
    oidc-provider fresh. This is achieved by pointing
    'OIDC_AFTER_USERLOGIN_HOOK' setting to this."""
    request.session.modified = True

    last_login_backend = request.session.get('social_auth_last_login_backend')
    client_options = OidcClientOptions.objects.get(oidc_client=client)

    allowed_methods = client_options.login_methods.all()
    if allowed_methods is None:
        raise django.core.exceptions.PermissionDenied

    allowed_providers = set((x.provider_id for x in allowed_methods))
    if last_login_backend is not None:
        active_backend = user.social_auth.filter(provider=last_login_backend)

    if ((last_login_backend is None and user is not None)
            or (active_backend.exists() and active_backend.first().provider not in allowed_providers)):
        django_user_logout(request)
        next_page = request.get_full_path()
        return redirect_to_login(next_page, settings.get('OIDC_LOGIN_URL'))

    # Return None to continue the login flow
    return None
