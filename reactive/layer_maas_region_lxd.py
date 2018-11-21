from subprocess import call

from charms.reactive import (
    when,
    when_not,
    when_any,
    set_flag,
    clear_flag,
    endpoint_from_flag,
    is_flag_set,
    hook,
    set_state,
)

from charmhelpers.core.hookenv import (
    config,
    leader_get,
    open_port,
    status_set,
    unit_get,
)

from charmhelpers.core.host import service_running, service_start

import charms.apt

from charmhelpers.core import unitdata

import charms.leadership

PRIVATE_IP = unit_get('private-address')
MAAS_WEB_PORT = 5240

kv = unitdata.kv()


def maas_url():
    if config('maas-url'):
        return config('maas-url')
    else:
        return 'http://{}:5240/MAAS'.format(PRIVATE_IP)


@when_not('layer-maas-region-lxd.installed')
def install_layer_maas_region_lxd():
    charms.apt.queue_install(['maas-region-api'])
    set_flag('layer-maas-region-lxd.installed')


@when('postgresql.connected',
      'apt.installed.maas-region-api')
@when_not('maas.database.requested')
def request_postgresql_database_for_maas_region(pgsql):
    """Request PGSql DB
    """

    conf = config()
    status_set('maintenance', 'Requesting MAASDB')

    pgsql.set_database(conf.get('db-name', 'maasdb'))
    if conf.get('db-roles'):
        pgsql.set_roles(conf.get('db-roles'))
    if conf.get('db-extensions'):
        pgsql.set_extensions(conf.get('db-extensions'))
    status_set('active', 'MAASDB requested')
    set_flag('maas.database.requested')


@when('postgresql.master.available',
      'maas.database.requested')
    #   'apt.installed.maas-region-api')
@when_not('maas.juju.database.available')
def get_set_postgresql_data_for_maas_db(pgsql):
    """Get/set postgresql details
    """

    status_set('maintenance', 'Database acquired, saving details')
    kv.set('db_host', pgsql.master.host)
    kv.set('db_name', pgsql.master.dbname)
    kv.set('db_pass', pgsql.master.password)
    kv.set('db_user', pgsql.master.user)
    status_set('active', 'MAASDB saved to unitdata')

    clear_flag('maas.manual.database.available')
    set_flag('maas.juju.database.available')


@when('apt.installed.maas-region-api',
      'leadership.is_leader')
@when_any('maas.juju.database.available',
          'maas.manual.database.available')
@when_not('maas.init.complete')
def maas_leader_init():
    """Init MAAS (region, region+rack) - only leader should run this code
    """
    status_set('maintenance',
               'Configuring MAAS-Region')

    init_ctxt = {'maas_url': maas_url(),
                #  'maas_mode': config('maas-mode'),
                 'db_host': kv.get('db_host'),
                 'db_name': kv.get('db_name'),
                 'db_pass': kv.get('db_pass'),
                 'db_user': kv.get('db_user')}
    cmd_init = ('maas-region local_config_set '
                '--maas-url {maas_url} --database-host {db_host} '
                '--database-name {db_name} --database-user {db_user} '
                '--database-pass {db_pass} '.format(**init_ctxt))
    cmd_dbupgrade = ('maas-region dbupgrade'.format(**init_ctxt))
    # cmd_init = ('maas init --maas-url {maas_url} --database-host {db_host} '
    #             '--database-name {db_name} --database-user {db_user} '
    #             '--database-pass {db_pass} --mode {maas_mode} '
    #             '--force'.format(**init_ctxt))
    call(cmd_init.split())
    call(cmd_dbupgrade.split())
    status_set('active', 'MAAS-Region configured')
    set_flag('maas.init.complete')


@when('leadership.is_leader',
      'maas.init.complete')
@when_not('maas.admin.created',
          'leadership.set.init_complete')
def create_maas_admin():
    """Create MAAS admin
    """
    super_user_ctxt = {'admin_password': config('admin-password'),
                       'admin_username': config('admin-username'),
                       'admin_email': config('admin-email')}

    cmd_create_super_user = ('maas init --admin-username {admin_username} '
                             '--admin-password {admin_password} '
                             '--admin-email {admin_email}'
                             .format(**super_user_ctxt))
    call(cmd_create_super_user.split())
    # Now the admin is created, init is complete
    charms.leadership.leader_set(init_complete="true")
    set_flag('maas.admin.created')


@when('maas.admin.created')
def start_maas_regiond_service():
    ''' Start the maas-regiond service. '''
    status_set('maintenance', 'Starting maas-regiond service.')
    if service_running('maas-regiond'):
        set_state('maas-regiond.service.started')
    else:
        service_start('maas-regiond')
    set_state('maas-regiond.service.started')


@when('leadership.is_leader',
      'maas-regiond.service.started')
@when_not('leadership.set.secret')
def get_set_secret():
    with open("/var/lib/maas/secret", 'r') as f:
        charms.leadership.leader_set(secret=f.read())


@when('leadership.set.secret')
@when_not('leadership.is_leader',
          'maas.init.complete')
@when_any('maas.juju.database.available',
          'maas.manual.database.available')
def init_non_leader_region_or_region_rack():
    status_set('maintenance',
               'Configuring MAAS-Region')

    init_ctxt = {'maas_url': maas_url(),
                #  'maas_mode': config('maas-mode'),
                 'db_host': kv.get('db_host'),
                 'db_name': kv.get('db_name'),
                 'db_pass': kv.get('db_pass'),
                 'db_user': kv.get('db_user')}

    cmd_init = ('maas-region local_config_set '
                '--maas-url {maas_url} --database-host {db_host} '
                '--database-name {db_name} --database-user {db_user} '
                '--database-pass {db_pass} --mode {maas_mode} '
                '--force'.format(**init_ctxt))

    call(cmd_init.split())

    status_set('active', 'MAAS-Region configured')
    set_flag('maas.init.complete')


@when('maas.init.complete')
@when_not('maas.http.available')
def open_web_port():
    open_port(MAAS_WEB_PORT)
    status_set('active', 'MAAS http available')
    set_flag('maas.http.available')


@when('leadership.set.secret',
      'leadership.is_leader',
      'endpoint.region.available')
@when_not('region.relation.data.available')
def send_relation_data_to_rack():
    endpoint = endpoint_from_flag('endpoint.region.available')
    ctxt = {'secret': leader_get('secret'),
            'maas_url': maas_url()}
    endpoint.configure(**ctxt)
    set_flag('region.relation.data.available')


# @when('apt.installed.maas-region-api')
# @when_not('maas.manual.database.available',
#           'maas.juju.database.available')
# def block_until_database_info_set():
#     """Block region-controller has set database info
#     """
#     status_set('blocked',
#                'Need database connection info via config or relation')
#     return


@when('endpoint.http.joined')
    #   'apt.installed.maas-region-api')
@when_not('http.relation.data.available')
def set_http_relation_data():
    endpoint = endpoint_from_flag('endpoint.http.joined')
    ctxt = {'host': PRIVATE_IP, 'port': MAAS_WEB_PORT}
    endpoint.configure(**ctxt)
    set_flag('http.relation.data.available')


@when('config.changed.maas-url',
      'maas.init.complete')
def react_to_config_changed_maas_url():
    status_set('maintenance',
               'Reconfiguring maas-url')
    call('maas config --maas-url {}'.format(maas_url()).split())
    status_set('active',
               'maas-url reconfigured to {}'.format(maas_url()))
