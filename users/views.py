import re

import requests
from urllib.parse import urlparse, parse_qs

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect, Http404, JsonResponse
from django.views.generic import FormView
from django.views.generic.base import TemplateView, View
from django.core.urlresolvers import reverse
from django.utils.http import quote
from django.shortcuts import redirect
from django.contrib.auth import logout as auth_logout

from allauth.socialaccount import providers
from django.views.generic.detail import SingleObjectTemplateResponseMixin
from django.views.generic.edit import BaseUpdateView
from oauth2_provider.models import get_application_model
from thesaurus.models import Concept, Member

from users.forms import ProfileForm
from .models import LoginMethod, Profile


class LoginView(TemplateView):
    template_name = "login.html"

    def get(self, request, *args, **kwargs):
        next_url = request.GET.get('next')
        app = None
        if next_url:
            # Determine application from the 'next' query argument.
            # FIXME: There should be a better way to get the app id.
            params = parse_qs(urlparse(next_url).query)
            client_id = params.get('client_id')
            if client_id and len(client_id):
                client_id = client_id[0].strip()
            if client_id:
                try:
                    app = get_application_model().objects.get(client_id=client_id)
                except get_application_model().DoesNotExist:
                    pass
            next_url = quote(next_url)

        if app:
            allowed_methods = app.login_methods.all()
        else:
            allowed_methods = LoginMethod.objects.all()

        provider_map = providers.registry.provider_map
        methods = []
        for m in allowed_methods:
            assert isinstance(m, LoginMethod)
            if m.provider_id == 'saml':
                continue  # SAML support removed
            else:
                provider_cls = provider_map[m.provider_id]
                provider = provider_cls(request)
                login_url = provider.get_login_url(request=self.request)
                if next_url:
                    login_url += '?next=' + next_url
            m.login_url = login_url
            methods.append(m)

        if len(methods) == 1:
            return redirect(methods[0].login_url)

        self.login_methods = methods
        return super(LoginView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(LoginView, self).get_context_data(**kwargs)
        context['login_methods'] = self.login_methods
        return context


class LogoutView(TemplateView):
    template_name = 'logout_done.html'

    def get(self, *args, **kwargs):
        if self.request.user.is_authenticated():
            auth_logout(self.request)
        url = self.request.GET.get('next')
        if url and re.match(r'http[s]?://', url):
            return redirect(url)
        return super(LogoutView, self).get(*args, **kwargs)


class EmailNeededView(TemplateView):
    template_name = 'email_needed.html'

    def get_context_data(self, **kwargs):
        context = super(EmailNeededView, self).get_context_data(**kwargs)
        reauth_uri = self.request.GET.get('reauth_uri', '')
        if '//' in reauth_uri:  # Prevent open redirect
            reauth_uri = ''
        context['reauth_uri'] = reauth_uri
        return context


class PushbulletView(TemplateView):
    template_name = "pushbullet.html"

    def get_profile(self):
        profile = None
        if self.request.user.is_authenticated():
            (profile, created) = Profile.objects.get_or_create(user=self.request.user)

        return profile

    def get(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated():
            return redirect('{}?next={}'.format(
                reverse('admin:login'),
                reverse('pushbullet'),
            ))

        if request.GET.get('code'):
            r = requests.post(
                'https://api.pushbullet.com/oauth2/token',
                json={
                    'code': request.GET.get('code'),
                    'grant_type': 'authorization_code',
                    'client_id': settings.PUSHBULLET_CLIENT_ID,
                    'client_secret': settings.PUSHBULLET_CLIENT_SECRET,
                },
                headers={
                    'Authorization': settings.PUSHBULLET_ACCESS_TOKEN,
                    'Content-Type': 'application/json'
                }
            )

            response_data = r.json()

            if 'access_token' in response_data and response_data.get('access_token'):
                profile = self.get_profile()
                profile.pushbullet_access_token = response_data.get('access_token')
                profile.save()

                return redirect(reverse('pushbullet'))

        return super(PushbulletView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(PushbulletView, self).get_context_data(**kwargs)

        profile = self.get_profile()

        context['profile'] = profile
        context['pushbullet_url'] = 'https://www.pushbullet.com/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code'.format(
            client_id=settings.PUSHBULLET_CLIENT_ID,
            redirect_uri=self.request.build_absolute_uri().replace('http:', 'https:'),  # ngrok kludge
        )

        return context


class ProfileView(LoginRequiredMixin, SingleObjectTemplateResponseMixin, BaseUpdateView):
    template_name = "profile.html"
    form_class = ProfileForm
    model = Profile

    def get_profile(self):
        profile = None
        if self.request.user.is_authenticated():
            (profile, created) = Profile.objects.get_or_create(user=self.request.user)

        return profile

    def get_object(self):
        return self.get_profile()

    def form_valid(self, form):
        self.object = form.save()

        return HttpResponseRedirect(reverse('profile'))


def get_concepts(request):
    if not request.user.is_authenticated or not request.user.is_active or not request.user.is_staff:
        raise Http404

    vocabulary_id = request.GET.get('vocabulary_id')
    parent_id = request.GET.get('parent_id')
    ids = request.GET.get('ids')

    if ids:
        ids = [int(i) for i in ids.split(',')]

    qs = Member.objects.all()

    if vocabulary_id:
        qs = qs.filter(concept__vocabulary_id=vocabulary_id)

    if ids:
        qs = qs.filter(concept__id__in=ids)

    if parent_id:
        qs = qs.filter(parent_id=parent_id)
    elif not ids:
        qs = qs.filter(parent_id__isnull=True)

    concepts = []
    for member in qs.select_related('concept'):
        concepts.append({
            'id': member.concept.id,
            'member_id': member.id,
            'parent_id': member.parent_id,
            'label': member.concept.safe_translation_getter("label", any_language=True),
        })

    return JsonResponse(concepts, safe=False)
