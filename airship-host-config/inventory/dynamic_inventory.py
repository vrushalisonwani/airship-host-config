#!/usr/bin/env python3

import os
import sys
import argparse
import time
import base64
import kubernetes.client
from kubernetes.client.rest import ApiException
import yaml

import json

interested_labels_annotations = ["beta.kubernetes.io/arch", "beta.kubernetes.io/os", "kubernetes.io/arch", "kubernetes.io/hostname", "kubernetes.io/os", "kubernetes.io/role", "topology.kubernetes.io/region", "topology.kubernetes.io/zone", "projectcalico.org/IPv4Address", "projectcalico.org/IPv4IPIPTunnelAddr", "Kernel Version", "OS Image", "Operating System", "Container Runtime Version", "Kubelet Version", "Operating System"]

class KubeInventory(object):

    def __init__(self):
        self.inventory = {}
        self.read_cli_args()

        self.api_instance = kubernetes.client.CoreV1Api(kubernetes.config.load_incluster_config())
        if self.args.list:
            self.kube_inventory()
        elif self.args.host:
            # Not implemented, since we return _meta info `--list`.
            self.inventory = self.empty_inventory()
        # If no groups or vars are present, return an empty inventory.
        else:
            self.inventory = self.empty_inventory()

        print(json.dumps(self.inventory, sort_keys=True, indent=4))

    # Kube driven inventory
    def kube_inventory(self):
        self.inventory = {"group": {"hosts": [], "vars": {}}, "_meta": {"hostvars": {}}}
        self.get_nodes()

    # Sets the ssh username and password using the pod environment variables
    def _set_ssh_keys(self, labels, node_internalip):
        namespace = ""
        if "SECRET_NAMESPACE" in os.environ:
            namespace = os.environ.get("SECRET_NAMESPACE")
        else:
            namespace = "default"
        if "secret" in labels.keys():
            try:
                secret_value = self.api_instance.read_namespaced_secret(labels["secret"], namespace)
            except ApiException as e:
                return False
            if "username" in secret_value.data.keys():
                username = (base64.b64decode(secret_value.data['username'])).decode("utf-8")
                self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_user"] = username
            elif "USER" in os.environ:
                self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_user"] = os.environ.get("USER")
            else:
                self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_user"] = 'kubernetes'
            if "password" in secret_value.data.keys():
                password = (base64.b64decode(secret_value.data['password'])).decode("utf-8")
                self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_pass"] = password
            elif "PASS" in os.environ:
                self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_pass"] =  os.environ.get("PASS")
            else:
                self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_pass"] = 'kubernetes'
        else:
            return False
        return True

    def _set_default_ssh_keys(self, node_internalip):
        if "USER" in os.environ:
            self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_user"] = os.environ.get("USER")
        else:
            self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_user"] = 'kubernetes'
        if "PASS" in os.environ:
            self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_pass"] =  os.environ.get("PASS")
        else:
            self.inventory["_meta"]["hostvars"][node_internalip]["ansible_ssh_pass"] = 'kubernetes'
        return

    # Gets the Kubernetes nodes labels and annotations and build the inventory
    # Also groups the kubernetes nodes based on the labels and annotations
    def get_nodes(self):
        #label_selector = "kubernetes.io/role="+role

        try:
            nodes = self.api_instance.list_node().to_dict()[
                "items"
            ]
        except ApiException as e:
            print("Exception when calling CoreV1Api->list_node: %s\n" % e)

        for node in nodes:
            addresses = node["status"]["addresses"]
            for address in addresses:
                if address["type"] == "InternalIP":
                    node_internalip = address["address"]
                    break
            else:
                node_internalip = None
            self.inventory["group"]["hosts"].append(node_internalip)

            self.inventory["_meta"]["hostvars"][node_internalip] = {}
            if not self._set_ssh_keys(node["metadata"]["labels"], node_internalip):
                self._set_default_ssh_keys(node_internalip)
            for key, value in node["metadata"]["annotations"].items():
                self.inventory["_meta"]["hostvars"][node_internalip][key] = value
            for key, value in node["metadata"]["labels"].items():
                self.inventory["_meta"]["hostvars"][node_internalip][key] = value
                if key in interested_labels_annotations:
                    if key+'_'+value not in self.inventory.keys():
                        self.inventory[key+'_'+value] = {"hosts": [], "vars": {}}
                    if node_internalip not in self.inventory[key+'_'+value]["hosts"]:
                        self.inventory[key+'_'+value]["hosts"].append(node_internalip)
            for key, value in node['status']['node_info'].items():
                self.inventory["_meta"]["hostvars"][node_internalip][key] = value
                if key in interested_labels_annotations:
                    if key+'_'+value not in self.inventory.keys():
                        self.inventory[key+'_'+value] = {"hosts": [], "vars": {}}
                    if node_internalip not in self.inventory[key+'_'+value]["hosts"]:
                        self.inventory[key+'_'+value]["hosts"].append(node_internalip)
            self.inventory["_meta"]["hostvars"][node_internalip][
                "kube_node_name"
            ] = node["metadata"]["name"]
        return

    def empty_inventory(self):
        return {"_meta": {"hostvars": {}}}

    # Read the command line args passed to the script.
    def read_cli_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--list", action="store_true")
        parser.add_argument("--host", action="store")
        self.args = parser.parse_args()


# Do computer.
KubeInventory()

