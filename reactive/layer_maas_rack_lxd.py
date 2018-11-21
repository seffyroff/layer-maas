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
)

from charmhelpers.core.hookenv import (
    config,
    leader_get,
    open_port,
    status_set,
    unit_get,
)

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


@when_not('layer-maas-rack-lxd.installed')
def install_layer_maas_rack_lxd():
    charms.apt.queue_install(['maas-rack-controller'])
    set_flag('layer-maas-rack-lxd.installed')


@when('apt.installed.maas-rack-controller',
      'endpoint.rack.joined')
@when_not('rack.relation.data.available')
def acquire_config_from_region_controller():
    """Acquire maas_url and secret from region
    """
    status_set('maintenance',
               'Acquiring configuration details from region controller')
    endpoint = endpoint_from_flag('endpoint.rack.joined')
    for unit in endpoint.list_unit_data():
        kv.set('maas_url', unit['maas_url'])
        kv.set('secret', unit['secret'])
    status_set('active', 'Region configuration acquired')
    set_flag('rack.relation.data.available')


@when('rack.relation.data.available')
@when_not('maas.init.complete')
def configure_maas_rack():
    """Configure rack controller now that we have what we need
    """
    status_set('maintenance', 'Rack initializing')
    init_ctxt = {'maas_url': kv.get('maas_url'),
                 'secret': kv.get('secret')}
    cmd_init = \
        ('maas-rack register --url {maas_url} --secret {secret} '
         .format(**init_ctxt))
    call(cmd_init.split())
    status_set('active', 'Rack init complete')
    set_flag('maas.init.complete')


@when('maas.init.complete')
def set_connected_status():
    status_set('active', "Region <-> Rack connected")


@when('apt.installed.maas-rack-controller')
@when_not('rack.relation.data.available')
def block_until_region_relation():
    """Block rack controllers until relation to region is acquired
    """
    status_set('blocked',
               'Need relation to region controller to continue')
    return


@when('config.changed.maas-url',
      'maas.init.complete')
def react_to_config_changed_maas_url():
    status_set('maintenance',
               'Reconfiguring maas-url')
    call('maas config --maas-url {}'.format(maas_url()).split())
    status_set('active',
               'maas-url reconfigured to {}'.format(maas_url()))
