from cStringIO import StringIO

from fabric.context_managers import shell_env
from fabric.operations import run
from fabric.operations import sudo, put
from nginx_parse_emit import emit, utils
from nginxparser import dumps, loads
from offregister_certificate import ubuntu as certificate
from offregister_fab_utils.apt import apt_depends
from offregister_fab_utils.ubuntu.systemd import restart_systemd
from offregister_nginx import ubuntu as nginx


def install0(*args, **kwargs):
    if run('dpkg -s matrix-synapse', quiet=True, warn_only=True).failed:
        sudo('add-apt-repository https://matrix.org/packages/debian/')
        sudo('wget -qO - https://matrix.org/packages/debian/repo-key.asc | sudo apt-key add -')
        with shell_env(DEBIAN_FRONTEND='noninteractive'):
            sudo('echo matrix-synapse matrix-synapse/server-name string {server_name} | debconf-set-selections'.format(
                server_name=kwargs['SERVER_NAME']))
            sudo(
                'echo matrix-synapse matrix-synapse/report-stats boolean {report_stats} | debconf-set-selections'.format(
                    report_stats=('false', 'true')[kwargs.get('REPORT_STATS', False)])
            )
            apt_depends('matrix-synapse')
        sudo('systemctl enable matrix-synapse')
        return 'installed'
    return 'already installed'


def restart1(*args, **kwargs):
    return restart_systemd('matrix-synapse')


def configure_nginx2(*args, **kwargs):
    kwargs.setdefault('LISTEN_PORT', 80)

    nginx.install_nginx0()
    nginx.setup_nginx_init1()

    if kwargs.get('self_signed', False):
        certificate.self_signed0(use_sudo=True, **kwargs)

    server_block = utils.merge_into(
        (lambda server_block: utils.apply_attributes(server_block,
                                                     emit.secure_attr(kwargs['SSL_CERTOUT'],
                                                                      kwargs['SSL_KEYOUT'])
                                                     ) if kwargs['LISTEN_PORT'] == 443 else server_block)(
            emit.server_block(server_name=kwargs['SERVER_NAME'],
                              listen=kwargs['LISTEN_PORT'])
        ),
        emit.api_proxy_block('/_matrix', 'https://127.0.0.1:8008')
    )

    sio = StringIO()
    sio.write(dumps(
        loads(emit.redirect_block(server_name=kwargs['SERVER_NAME'], port=80)) + server_block
        if kwargs['LISTEN_PORT'] == 443 else server_block
    ))

    put(sio,
        '/etc/nginx/sites-enabled/{server_name}'.format(server_name=kwargs['SERVER_NAME']),
        use_sudo=True, )
    return restart_systemd('nginx')
