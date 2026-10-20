#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2017-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import ipaddress
import socket
import subprocess
from typing import Iterable, List, Set

import dns.resolver


def _srv_query(name: str) -> list:
    # dnspython < 2.0 (e.g. RHEL 8's python3-dns) only knows query(),
    # newer versions renamed it to resolve().
    resolver = dns.resolver.Resolver()
    query = getattr(resolver, 'resolve', None) or resolver.query
    return list(query(name, 'SRV'))


def get_master_ip_through_dns(domain: str) -> str:
    try:
        response = _srv_query('_domaincontroller_master._tcp.%s.' % (domain,))
        master_fqdn = response[0].target.canonicalize().split(1)[0].to_text()
    except Exception:
        return ""
    return socket.gethostbyname(master_fqdn)


def get_ucs_domainname() -> str:
    domainname = get_ucs_domainname_via_local_configuration()
    if not domainname:
        domainname = get_ucs_domainname_via_reverse_dns()
    if not domainname:
        domainname = get_ucs_domainname_of_dns_server()
    return domainname


def get_ucs_domainname_via_local_configuration() -> str:
    try:
        domainname = socket.getfqdn().split('.', 1)[1]
    except Exception:
        return ""
    return domainname


def get_ucs_domainname_via_reverse_dns() -> str:
    return ips2name(get_all_ip_addresses())


def get_ucs_domainname_of_dns_server() -> str:
    return ips2name(get_nameservers())


def get_nameservers() -> Set[str]:
    nameservers = set()
    try:
        with open('/etc/resolv.conf') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == 'nameserver' and is_only_ip(parts[1]):
                    nameservers.add(parts[1])
    except IOError:
        pass
    return nameservers


def is_only_ip(line: str) -> bool:
    try:
        ipaddress.ip_address(line.strip())
        return True
    except ValueError:
        return False


def get_all_ip_addresses() -> List[str]:
    # Parse `ip -o addr show` instead of using netifaces, which is not
    # packaged for all RPM distributions.
    ip_addresses = []
    try:
        output = subprocess.check_output(['ip', '-o', 'addr', 'show']).decode()
    except (OSError, subprocess.CalledProcessError):
        return ip_addresses
    for line in output.splitlines():
        parts = line.split()
        try:
            family_index = next(i for i, p in enumerate(parts) if p in ('inet', 'inet6'))
        except StopIteration:
            continue
        if parts[1] == 'lo':
            continue
        if 'scope' in parts and parts[parts.index('scope') + 1] == 'link':
            continue  # skip link-local IPv6 addresses
        ip_addresses.append(parts[family_index + 1].split('/')[0])
    return ip_addresses


def ips2name(addrs: Iterable[str]) -> str:
    for addr in addrs:
        fqdn = socket.getfqdn(addr)
        domainname = get_ucs_domainname_from_fqdn(fqdn)
        if domainname:
            return domainname
    return ""


def get_ucs_domainname_from_fqdn(fqdn: str) -> str:
    try:
        domainname = fqdn.split('.', 1)[1]
        # Check if the _domaincontroller_master._tcp record exists, to ensure
        # that this is an UCS domain.
        _srv_query('_domaincontroller_master._tcp.%s' % (domainname,))
    except Exception:
        return ""
    return domainname
