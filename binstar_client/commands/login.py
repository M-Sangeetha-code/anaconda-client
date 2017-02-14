'''
Authenticate a user
'''
from __future__ import unicode_literals

import getpass
import logging
import socket
import sys
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse
from binstar_client import errors
from binstar_client.utils import get_config, get_server_api, store_token, \
    bool_input
import platform


log = logging.getLogger('binstar.login')

try:
    input = raw_input
except NameError:
    input = input


def try_replace_token(authenticate, **kwargs):
    '''
    Authenticates using the given *authenticate*, retrying if the token needs
    to be replaced.
    '''

    try:
        return authenticate(**kwargs)
    except errors.BinstarError as err:
        if kwargs.get('fail_if_already_exists') and len(err.args) > 1 and err.args[1] == 400:
            log.warn('It appears you are already logged in from host %s' % socket.gethostname())
            log.warn('Logging in again will remove the previous token. '
                     ' (This could cause troubles with virtual machines with the same hostname)')
            log.warn('Otherwise you can login again and specify a '
                      'different hostname with "--hostname"')
            if bool_input("Would you like to continue"):
                kwargs['fail_if_already_exists'] = False
                return authenticate(**kwargs)

        raise


def interactive_get_token(args, fail_if_already_exists=True):
    bs = get_server_api(args.token, args.site, args.log_level)
    config = get_config(remote_site=args.site)

    token = None
    # This function could be called from a totally different CLI, so we don't
    # know if the attribute hostname exists.
    hostname = getattr(args, 'hostname', platform.node())
    site = args.site or config.get('default_site')
    url = config.get('url', 'https://api.anaconda.org')

    auth_name = 'binstar_client:'
    if site and site != 'binstar':
        # For testing with binstar alpha site
        auth_name += '%s:' % site

    auth_name += '%s@%s' % (getpass.getuser(), hostname)

    bs.check_server()
    auth_type = bs.authentication_type()

    if auth_type == 'kerberos':
        token = try_replace_token(
            bs.krb_authenticate,
            application=auth_name,
            application_url=url,
            created_with=' '.join(sys.argv),
            fail_if_already_exists=fail_if_already_exists,
            hostname=hostname,
        )

        if token is None:
            raise errors.BinstarError(
                'Unable to authenticate via Kerberos. Try refreshing your '
                'authentication using `kinit`')

    else:

        if getattr(args, 'login_username', None):
            username = args.login_username
        else:
            username = input('Username: ')


        password = getattr(args, 'login_password', None)

        for _ in range(3):
            try:
                sys.stderr.write("%s's " % username)

                if password is None:
                    password = getpass.getpass(stream=sys.stderr)

                token = try_replace_token(
                    bs.authenticate,
                    username=username,
                    password=password,
                    application=auth_name,
                    application_url=url,
                    created_with=' '.join(sys.argv),
                    fail_if_already_exists=fail_if_already_exists,
                    hostname=hostname,
                )
                break

            except errors.Unauthorized:
                log.error('Invalid Username password combination, please try again')
                password = None
                continue


        if token is None:
            parsed_url = urlparse(url)
            if parsed_url.netloc.startswith('api.anaconda.org'):
                netloc = 'anaconda.org'
            else:
                netloc = parsed_url.netloc
            hostparts = (parsed_url.scheme, netloc)
            msg = ('Sorry. Please try again ' + \
                   '(go to %s://%s/account/forgot_password ' % hostparts + \
                   'to reset your password)')
            raise errors.BinstarError(msg)

    return token

def interactive_login(args):
    token = interactive_get_token(args)
    store_token(token, args)
    log.info('login successful')

def main(args):
    interactive_login(args)

def add_parser(subparsers):
    subparser = subparsers.add_parser('login',
                                      help='Authenticate a user',
                                      description=__doc__)
    subparser.add_argument('--hostname', default=platform.node(),
                           help="Specify the host name of this login, "
                                "this should be unique (default: %(default)s)"
                           )
    subparser.add_argument('--username',
                           dest='login_username',
                           help="Specify your username. "
                                "If this is not given, you will be prompted"
                           )
    subparser.add_argument('--password',
                           dest='login_password',
                           help="Specify your password. "
                                "If this is not given, you will be prompted"
                           )
    subparser.set_defaults(main=main)
