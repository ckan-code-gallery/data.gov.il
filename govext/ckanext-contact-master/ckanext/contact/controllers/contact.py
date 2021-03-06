import logging
import ckan.lib.base as base
import ckan.plugins as p
import ckan.logic as logic
import ckan.model as model
import ckan.lib.navl.dictization_functions as dictization_functions
import ckan.lib.mailer as mailer
import ckanext.gov_theme.mailer as custom_mailer
import ckan.lib.helpers as h
import socket
from pylons import config
from ckan.common import _, request, c, response
from ckanext.contact.interfaces import IContact
import ckanext.gov_theme.captcha as captcha


log = logging.getLogger(__name__)

render = base.render
abort = base.abort
#redirect = base.redirect

DataError = dictization_functions.DataError
unflatten = dictization_functions.unflatten

check_access = logic.check_access
get_action = logic.get_action
flatten_to_string_key = logic.flatten_to_string_key

class ContactController(base.BaseController):
    """
    Controller for displaying a contact form
    """

    def __before__(self, action, **env):

        super(ContactController, self).__before__(action, **env)
        if "form" in request.GET:
            if "data_request" in request.GET.getone('form'):
                c.contact_title = _('Data Request')
            else:
                c.contact_title = _('Contact Us')
        else:
            c.contact_title = _('Contact Us')
        try:
            self.context = {'model': model, 'session': model.Session, 'user': base.c.user or base.c.author, 'auth_user_obj': base.c.userobj}
            check_access('send_contact', self.context)
        except logic.NotAuthorized:
            base.abort(401, _('Not authorized to use contact form'))

    @staticmethod
    def _submit(context):

        errors = {}
        error_summary = {}

        try:
            data_dict = logic.clean_dict(unflatten(logic.tuplize_dict(logic.parse_params(request.params))))
            context['message'] = data_dict.get('log_message', '')
            c.form = data_dict['name']
            if (config.get('ckan.recaptcha.is_enabled')) == "True":
                if not (captcha.check_recaptcha(request)):
                    raise captcha.CaptchaError
        except logic.NotAuthorized:
            base.abort(401, _('Not authorized to see this page'))
        except captcha.CaptchaError:
            errors['captcha'] = [_(u'Bad Captcha. Please try again.')]
            error_summary[_('captcha')] = _(u'Bad Captcha. Please try again.')

        if data_dict["email"] == '':
            errors['email'] = [_(u'Missing value')]
            error_summary[_('email')] = _(u'Missing value')

        if data_dict["name"] == '':
            errors['name'] = [_(u'Missing value')]
            error_summary[_('Contact Name')] = _(u'Missing value')

        if data_dict["content"] == '':
            errors['content'] = [_(u'Missing value')]
            error_summary[_('request')] = _(u'Missing value')

        if c.contact_title == _('Data Request'):
            body_title = _('A data request form is recieved')
            mail_subject = _('Data Request - Government Data')
        else:
           body_title = _('A contact form is recieved')
           mail_subject = _('Contact - Government Data')

        if len(errors) == 0:

            body = _('Hello')+","
            body += '\n'+body_title
            body += '\n'+_(u'First name and surname')+":"+data_dict["name"]
            body += '\n'+_(u'Email')+":"+data_dict["email"]
            if c.contact_title == _('Data Request'):
                body += '\n' + _(u'organization_name') + ':' + data_dict["organizations"]
            body += '\n'+_(u'Message')+':'+data_dict["content"]
            body += '\n\n'+_(u'Best Regards')
            body += '\n'+_(u'Government Data Site')

            mail_dict = {
                'recipient_email': config.get('email_to'),
                'recipient_name': config.get("ckanext.contact.recipient_name", config.get('ckan.site_title')),
                'subject': config.get("ckanext.contact.subject", mail_subject),
                'body': body,
                'headers': {'reply-to': data_dict["email"]}
            }

            # Allow other plugins to modify the mail_dict
            for plugin in p.PluginImplementations(IContact):
                plugin.mail_alter(mail_dict, data_dict)

            try:
                custom_mailer.mail_recipient(**mail_dict)
            except (mailer.MailerException, socket.error):
                h.flash_error(_(u'Sorry, there was an error sending the email. Please try again later'))
            else:
                data_dict['success'] = True

        return data_dict, errors, error_summary

    def ajax_submit(self):
        """
        AJAX form submission
        @return:
        """
        data, errors, error_summary = self._submit(self.context)
        data = flatten_to_string_key({'data': data, 'errors': errors, 'error_summary': error_summary})
        response.headers['Content-Type'] = 'application/json;charset=utf-8'
        return h.json.dumps(data)

    def form(self):

        """
        Return a contact form
        :return: html
        """

        data = {}
        errors = {}
        error_summary = {}

        # Submit the data
        if 'save' in request.params:
            data, errors, error_summary = self._submit(self.context)
        else:
            # Try and use logged in user values for default values
            try:
                data['name'] = base.c.userobj.fullname or base.c.userobj.name
                data['email'] = base.c.userobj.email
            except AttributeError:
                data['name'] = data['email'] = None

        if data.get('success', False):
            return p.toolkit.render('contact/success.html')
        else:
            vars = {'data': data, 'errors': errors, 'error_summary': error_summary}
            return p.toolkit.render('contact/form.html', extra_vars=vars)
