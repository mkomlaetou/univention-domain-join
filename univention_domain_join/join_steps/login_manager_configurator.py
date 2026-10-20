#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2017-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
import os
from shutil import copyfile

from univention_domain_join.utils.general import execute_as_root

userinfo_logger = logging.getLogger('userinfo')

# On RPM based distributions the login manager is selected through the
# display-manager.service symlink (Debian/Ubuntu use
# /etc/X11/default-display-manager instead).
DISPLAY_MANAGER_SERVICE = '/etc/systemd/system/display-manager.service'


class ConflictChecker(object):
    def configuration_conflicts(self) -> bool:
        login_manager = self.determine_used_login_manager()
        if login_manager is None:
            userinfo_logger.info('No display manager found (headless system?). Nothing to configure.')
            return False
        if login_manager in ('lightdm', 'gdm', 'gdm3', 'sddm'):
            return False
        userinfo_logger.error('Error: Can\'t enable login with the login manager of your system (%s).' % login_manager)
        userinfo_logger.error('       Please use LightDM, SDDM or GDM for full compatibility with UCS.')
        userinfo_logger.error('       This error can be avoided by using the --skip-login-manager parameter.')
        return True

    def determine_used_login_manager(self) -> str:
        if not os.path.exists(DISPLAY_MANAGER_SERVICE):
            return None
        return os.path.splitext(os.path.basename(os.path.realpath(DISPLAY_MANAGER_SERVICE)))[0]

    def lightdm_config_file_exists(self) -> bool:
        if os.path.isfile('/etc/lightdm/lightdm.conf.d/99-show-manual-userlogin.conf'):
            userinfo_logger.warn('Warning: /etc/lightdm/lightdm.conf.d/99-show-manual-userlogin.conf already exists.')
            return True
        return False


class LoginManagerConfigurator(ConflictChecker):

    @execute_as_root
    def backup(self, backup_dir: str) -> None:
        if self.lightdm_config_file_exists():
            os.makedirs(os.path.join(backup_dir, 'etc/lightdm/lightdm.conf.d'), exist_ok=True)
            copyfile(
                '/etc/lightdm/lightdm.conf.d/99-show-manual-userlogin.conf',
                os.path.join(backup_dir, 'etc/lightdm/lightdm.conf.d/99-show-manual-userlogin.conf')
            )

    def enable_login_with_foreign_usernames(self) -> None:
        login_manager = self.determine_used_login_manager()
        if login_manager == 'lightdm':
            self.enable_login_with_foreign_usernames_for_lightdm()
        # GDM supports typing arbitrary user names through its
        # "Not listed?" entry out of the box; SDDM accepts them in its
        # user name field as well.

    @execute_as_root
    def enable_login_with_foreign_usernames_for_lightdm(self) -> None:
        userinfo_logger.info('Writing /etc/lightdm/lightdm.conf.d/99-show-manual-userlogin.conf ')

        lightdm_config = \
            '[Seat:*]\n' \
            'greeter-show-manual-login=true\n' \
            'greeter-hide-users=true\n'

        os.makedirs('/etc/lightdm/lightdm.conf.d', exist_ok=True)
        with open('/etc/lightdm/lightdm.conf.d/99-show-manual-userlogin.conf', 'w') as conf_file:
            conf_file.write(lightdm_config)
