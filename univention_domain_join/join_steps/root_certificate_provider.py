#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2017-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
import os
import shutil
import subprocess

from univention_domain_join.utils.general import execute_as_root

userinfo_logger = logging.getLogger('userinfo')

# The UCS root certificate is kept at the same path as on Debian/Ubuntu
# clients, because sssd.conf and ldap.conf reference it.
UCS_CA_CERT = '/etc/univention/ssl/ucsCA/CAcert.pem'
# The system trust store anchor directory on RPM based distributions
# (Debian/Ubuntu use /usr/local/share/ca-certificates instead).
CA_TRUST_ANCHORS = '/etc/pki/ca-trust/source/anchors'
CA_TRUST_CERT = os.path.join(CA_TRUST_ANCHORS, 'UCSdomain.crt')


class RootCertificateProvider(object):
    def provide_ucs_root_certififcate(self, dc_ip: str) -> None:
        if not self.ucs_root_certificate_available_locally():
            self.download_ucs_root_certificate(dc_ip)
            self.add_certificate_to_certificate_store()

    def ucs_root_certificate_available_locally(self) -> bool:
        return os.path.isfile(UCS_CA_CERT) and os.path.isfile(CA_TRUST_CERT)

    @execute_as_root
    def download_ucs_root_certificate(self, dc_ip: str) -> None:
        userinfo_logger.info('Downloading the UCS root certificate to %s' % UCS_CA_CERT)

        os.makedirs(os.path.dirname(UCS_CA_CERT), exist_ok=True)
        url = 'http://%s/ucs-root-ca.crt' % (dc_ip,)
        if shutil.which('wget'):
            cmd = ['wget', '--no-check-certificate', '-O', UCS_CA_CERT, url]
        else:
            cmd = ['curl', '-k', '-o', UCS_CA_CERT, url]
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)

    @execute_as_root
    def add_certificate_to_certificate_store(self) -> None:
        userinfo_logger.info('Adding the UCS root certificate to the certificate store')

        os.makedirs(CA_TRUST_ANCHORS, exist_ok=True)
        shutil.copyfile(UCS_CA_CERT, CA_TRUST_CERT)
        subprocess.check_output(
            ['update-ca-trust', 'extract'],
            stderr=subprocess.STDOUT
        )
