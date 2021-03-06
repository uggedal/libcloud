# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# libcloud.org licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Softlayer driver
"""

import xmlrpclib

import libcloud
from libcloud.types import Provider
from libcloud.base import NodeDriver, Node, NodeLocation

API_PREFIX = "http://api.service.softlayer.com/xmlrpc/v3"

DATACENTERS = {
    'sea01': {'country': 'US'},
    'wdc01': {'country': 'US'},
    'dal01': {'country': 'US'}
}

class SoftLayerException(Exception):
    pass

class SoftLayerTransport(xmlrpclib.Transport):
    user_agent = "libcloud/%s (SoftLayer)" % libcloud.__version__

class SoftLayerProxy(xmlrpclib.ServerProxy):
    transportCls = SoftLayerTransport

    def __init__(self, service, verbose=0):
        xmlrpclib.ServerProxy.__init__(
            self,
            uri="%s/%s" % (API_PREFIX, service),
            transport=self.transportCls(use_datetime=0),
            verbose=verbose
        )

class SoftLayerConnection(object):
    proxyCls = SoftLayerProxy
    driver = None

    def __init__(self, user, key):
        self.user = user
        self.key = key 

    def request(self, service, method, *args, **init_params):
        sl = self.proxyCls(service)
        params = [self._get_auth_param(service, init_params)] + list(args)
        try:
            return getattr(sl, method)(*params)
        except xmlrpclib.Fault, e:
            raise SoftLayerException(e)

    def _get_auth_param(self, service, init_params=None):
        if not init_params:
            init_params = {}

        return {
            'headers': {
                'authenticate': {
                    'username': self.user,
                    'apiKey': self.key
                },
                '%sInitParameters' % service: init_params
            }
        }

class SoftLayerNodeDriver(NodeDriver):
    connectionCls = SoftLayerConnection
    name = 'SoftLayer'
    type = Provider.SOFTLAYER

    def __init__(self, key, secret=None, secure=False):
        self.key = key
        self.secret = secret
        self.connection = self.connectionCls(key, secret)
        self.connection.driver = self

    def _to_node(self, host):
        return Node(
            id=host['id'],
            name=host['hostname'],
            state=host['statusId'],
            public_ip=host['primaryIpAddress'],
            private_ip=host['primaryBackendIpAddress'],
            driver=self
        )
    
    def _to_nodes(self, hosts):
        return [self._to_node(h) for h in hosts]

    def destroy_node(self, node):
        billing_item = self.connection.request(
            "SoftLayer_Virtual_Guest",
            "getBillingItem",
            id=node.id
        )

        if billing_item:
            res = self.connection.request(
                "SoftLayer_Billing_Item",
                "cancelService",
                id=billing_item['id']
            )
            return res
        else:
            return False

    def create_node(self, **kwargs):
        """
        Right now the best way to create a new node in softlayer is by 
        cloning an already created node, so size and image do not apply.

        @keyword    node:   A Node which will serve as the template for the new node
        @type       node:   L{Node}

        @keyword    domain:   e.g. libcloud.org
        @type       domain:   str
        """
        name = kwargs['name']
        location = kwargs['location']
        node = kwargs['node']
        domain = kwargs['domain']

        res = self.connection.request(
            "SoftLayer_Virtual_Guest",
            "getOrderTemplate",
            "HOURLY",
            id=node.id
        )

        res['location'] = location.id
        res['complexType'] = 'SoftLayer_Container_Product_Order_Virtual_Guest'
        res['quantity'] = 1
        res['virtualGuests'] = [
            {
                'hostname': name,
                'domain': domain
            }
        ]

        res = self.connection.request(
            "SoftLayer_Product_Order",
            "placeOrder",
            res
        )

        return None # the instance won't be available for a while.

    def _to_loc(self, loc):
        return NodeLocation(
            id=loc['id'],
            name=loc['name'],
            country=DATACENTERS[loc['name']]['country'],
            driver=self
        )

    def list_locations(self):
        res = self.connection.request(
            "SoftLayer_Location_Datacenter",
            "getDatacenters"
        ) 

        # checking "in DATACENTERS", because some of the locations returned by getDatacenters are not useable.
        return [self._to_loc(l) for l in res if l['name'] in DATACENTERS]     

    def list_nodes(self):
        nodes = self._to_nodes(
            self.connection.request("SoftLayer_Account","getVirtualGuests")
        )
        return nodes

    def reboot_node(self, node):
        res = self.connection.request(
            "SoftLayer_Virtual_Guest", 
            "rebootHard", 
            id=node.id
        )
        return res
