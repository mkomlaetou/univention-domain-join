#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2017-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import grp
import logging
import os
import shutil
import subprocess
from shutil import copyfile

from univention_domain_join.utils.general import execute_as_root

userinfo_logger = logging.getLogger('userinfo')

GROUP_CONF = '/etc/security/group.conf'
# Name of the custom authselect profile this tool creates and selects.
AUTHSELECT_PROFILE = 'ucs'
AUTHSELECT_PROFILE_DIR = '/etc/authselect/custom/%s' % (AUTHSELECT_PROFILE,)
# Groups the domain users should become members of at login time, via
# pam_group. Groups that don't exist on the local system are skipped.
GROUPS_FOR_DOMAIN_USERS = ['audio', 'cdrom', 'dialout', 'floppy', 'adm', 'video']


class PamConfigurationException(Exception):
    pass


class ConflictChecker(object):
    def authselect_profile_exists(self) -> bool:
        if os.path.isdir(AUTHSELECT_PROFILE_DIR):
            userinfo_logger.warn('Warning: %s already exists.' % AUTHSELECT_PROFILE_DIR)
            return True
        return False


class PamConfigurator(ConflictChecker):

    @execute_as_root
    def backup(self, backup_dir: str) -> None:
        if os.path.isfile(GROUP_CONF):
            os.makedirs(os.path.join(backup_dir, 'etc/security'), exist_ok=True)
            copyfile(GROUP_CONF, os.path.join(backup_dir, 'etc/security/group.conf'))
        if os.path.isfile('/etc/nsswitch.conf'):
            os.makedirs(os.path.join(backup_dir, 'etc'), exist_ok=True)
            copyfile('/etc/nsswitch.conf', os.path.join(backup_dir, 'etc/nsswitch.conf'))
        # authselect rewrites these files when a profile is selected.
        for pam_file in ('system-auth', 'password-auth'):
            path = os.path.join('/etc/pam.d', pam_file)
            if os.path.isfile(path) and not os.path.islink(path):
                os.makedirs(os.path.join(backup_dir, 'etc/pam.d'), exist_ok=True)
                copyfile(path, os.path.join(backup_dir, 'etc/pam.d', pam_file))

    def setup_pam(self) -> None:
        self.add_users_to_required_system_groups()
        if shutil.which('authselect'):
            self.setup_authselect()
        elif shutil.which('authconfig'):
            self.setup_authconfig()
        else:
            userinfo_logger.critical('Neither authselect nor authconfig was found. Cannot configure PAM.')
            raise PamConfigurationException()
        self.enable_oddjobd()

    @execute_as_root
    def add_users_to_required_system_groups(self) -> None:
        groups = [g for g in GROUPS_FOR_DOMAIN_USERS if self.group_exists(g)]
        if not groups:
            return
        group_conf_line = '*;*;*;Al0000-2400;%s\n' % (','.join(groups),)
        if self.group_conf_already_ok(group_conf_line):
            return

        userinfo_logger.info('Adding groups to %s ' % GROUP_CONF)
        os.makedirs(os.path.dirname(GROUP_CONF), exist_ok=True)
        with open(GROUP_CONF, 'a') as groups_file:
            groups_file.write(group_conf_line)

    def group_exists(self, group: str) -> bool:
        try:
            grp.getgrnam(group)
            return True
        except KeyError:
            return False

    def group_conf_already_ok(self, group_conf_line: str) -> bool:
        try:
            with open(GROUP_CONF, 'r') as groups_file:
                return group_conf_line in groups_file.read().splitlines(keepends=True)
        except IOError:
            return False

    @execute_as_root
    def setup_authselect(self) -> None:
        self.create_authselect_profile()
        self.add_pam_group_to_authselect_profile()

        userinfo_logger.info('Selecting the authselect profile custom/%s with-mkhomedir' % AUTHSELECT_PROFILE)
        subprocess.check_output(
            ['authselect', 'select', 'custom/%s' % (AUTHSELECT_PROFILE,), 'with-mkhomedir', '--force'],
            stderr=subprocess.STDOUT
        )

    @execute_as_root
    def create_authselect_profile(self) -> None:
        if os.path.isdir(AUTHSELECT_PROFILE_DIR):
            return
        userinfo_logger.info('Creating authselect profile %s based on the sssd profile' % AUTHSELECT_PROFILE)
        shutil.copytree('/usr/share/authselect/default/sssd', AUTHSELECT_PROFILE_DIR, symlinks=True)

    @execute_as_root
    def add_pam_group_to_authselect_profile(self) -> None:
        userinfo_logger.info('Adding pam_group to the authselect profile %s' % AUTHSELECT_PROFILE)
        for pam_file in ('system-auth', 'password-auth'):
            path = os.path.join(AUTHSELECT_PROFILE_DIR, pam_file)
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                lines = f.readlines()
            if any('pam_group.so' in line for line in lines):
                continue
            pam_group_line = 'auth        required      pam_group.so use_first_pass\n'
            insert_at = next(
                (i for i, line in enumerate(lines)
                 if line.startswith('auth') and ('pam_unix.so' in line or 'pam_sss.so' in line)),
                len(lines)
            )
            lines.insert(insert_at, pam_group_line)
            with open(path, 'w') as f:
                f.writelines(lines)

    @execute_as_root
    def setup_authconfig(self) -> None:
        # Fallback for old distributions (RHEL 7 and alike) without authselect.
        userinfo_logger.info('Updating PAM via authconfig')
        subprocess.check_output(
            ['authconfig', '--enablesssd', '--enablesssdauth', '--enablemkhomedir', '--update'],
            stderr=subprocess.STDOUT
        )

    @execute_as_root
    def enable_oddjobd(self) -> None:
        # authselect's with-mkhomedir feature uses pam_oddjob_mkhomedir,
        # which needs a running oddjobd to actually create home directories.
        userinfo_logger.info('Enabling oddjobd for automatic home directory creation')
        subprocess.check_output(
            ['systemctl', 'enable', '--now', 'oddjobd'],
            stderr=subprocess.STDOUT
        )
