from django import forms
# from django.contrib.admin.widgets import ForeignKeyRawIdWidget
from django.utils.encoding import force_text
from munigeo.models import AdministrativeDivision
from thesaurus.models import Concept

from users.models import Profile


class CustomLabelField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        name = obj.name

        if not name:
            name = obj.ocd_id.split(':')[-1]

        return name


class ForeignKeyRawIdWidget(forms.TextInput):
    """
    A Widget for displaying ForeignKeys in the "raw_id" interface rather than
    in a <select> box.
    """
    template_name = 'admin/widgets/foreign_key_raw_id.html'

    def __init__(self, rel, attrs=None, using=None):
        self.rel = rel
        self.db = using
        super(ForeignKeyRawIdWidget, self).__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super(ForeignKeyRawIdWidget, self).get_context(name, value, attrs)
        rel_to = self.rel.model
        return context

    def label_and_url_for_value(self, value):
        key = self.rel.get_related_field().name
        try:
            obj = self.rel.model._default_manager.using(self.db).get(**{
                key: value
            })
        except (ValueError, self.rel.model.DoesNotExist):
            return '', ''

        return obj, ''


class ManyToManyRawIdWidget(ForeignKeyRawIdWidget):
    """
    A Widget for displaying ManyToMany ids in the "raw_id" interface rather than
    in a <select multiple> box.
    """
    template_name = 'admin/widgets/many_to_many_raw_id.html'

    def get_context(self, name, value, attrs):
        context = super(ManyToManyRawIdWidget, self).get_context(name, value, attrs)

        return context

    def value_from_datadict(self, data, files, name):
        value = data.get(name)
        if value:
            return value.split(',')

    def format_value(self, value):
        return ','.join(force_text(v) for v in value) if value else ''


class ProfileForm(forms.ModelForm):
    divisions_of_interest = CustomLabelField(queryset=AdministrativeDivision.objects.filter(type__type='district'))
    concepts_of_interest = forms.ModelMultipleChoiceField(queryset=Concept.objects.all(), widget=ManyToManyRawIdWidget(Profile._meta.get_field("concepts_of_interest").rel))

    class Meta:
        model = Profile
        fields = ['email', 'phone', 'language', 'contact_method', 'divisions_of_interest', 'concepts_of_interest']
