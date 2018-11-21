# Overview
Complete automation of your physical servers for amazing data centre operational efficiency. On premises, open source and supported.

# MAAS
- [MAAS Website](https://www.maas.io/)

# Usage
This charm can be used to deploy MAAS Region Controllers, and is designed to be used within LXD containers.

```bash
# Deploy postgresql
juju deploy postgresql

# Deploy each node
juju deploy maas-region-lxd

juju deploy maas-rack-lxd

# Relation between region and pgsql
juju relate maas-region-lxd:postgresql postgresql:db 

# Relation between region and rack
juju relate maas-region-lxd:region maas-rack-lxd:rack

```

You should now be able to visit `http://<maas-region-ip>:5240/MAAS` in your browser and see your maas nodes all checked in!


# Copyright
* AGPLv3 (see `copyright` file in this directory)

# Acknowledgements
Based on and with the support of James Beedy.
Thanks to everyone on #MAAS, #Juju and #lxcontainers, and their Discourse communities.