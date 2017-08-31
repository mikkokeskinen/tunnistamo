from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from munigeo.models import AdministrativeDivision
from oauth2_provider.models import get_application_model

from .models import User, LoginMethod, Profile

Application = get_application_model()


class ProfileAdmin(admin.StackedInline):
    model = Profile
    raw_id_fields = ('concepts_of_interest', )

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "divisions_of_interest":
            kwargs["queryset"] = AdministrativeDivision.objects.filter(type__type='peruspiiri')

        formfield = super(ProfileAdmin, self).formfield_for_manytomany(db_field, request, **kwargs)

        return formfield


class ExtendedUserAdmin(UserAdmin):
    search_fields = ['username', 'uuid', 'email', 'first_name', 'last_name']
    list_display = search_fields + ['is_active', 'is_staff', 'is_superuser']
    inlines = [ProfileAdmin]

    def get_fieldsets(self, request, obj=None):
        fieldsets = super(ExtendedUserAdmin, self).get_fieldsets(request, obj)
        new_fieldsets = []
        for (name, field_options) in fieldsets:
            fields = list(field_options.get('fields', []))
            if 'username' in fields:
                fields.insert(fields.index('username'), 'uuid')
                field_options = dict(field_options, fields=fields)
            new_fieldsets.append((name, field_options))
        return new_fieldsets

    def get_readonly_fields(self, request, obj=None):
        fields = super(ExtendedUserAdmin, self).get_readonly_fields(
            request, obj)
        return list(fields) + ['uuid']

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super(ExtendedUserAdmin, self).formfield_for_dbfield(
            db_field, request, **kwargs)
        if db_field.name == 'username':
            # Allow username be filled from uuid in
            # helusers.models.AbstractUser.clean
            field.required = False
        return field


admin.site.register(User, ExtendedUserAdmin)


@admin.register(LoginMethod)
class LoginMethodAdmin(admin.ModelAdmin):
    model = LoginMethod


class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'site_type')
    list_filter = ('site_type',)
    model = Application

admin.site.unregister(Application)
admin.site.register(Application, ApplicationAdmin)
