# Univention Domain Join — RPM edition

This is a port of [univention-domain-join](https://github.com/univention/univention-domain-join)
(`ubuntu24.04` branch) to RPM based Linux distributions. It is an assistant for
joining client computers into Univention Corporate Server (UCS) domains. It will
perform the following steps for you:

- Create an LDAP object for your computer on UCS (UDM type `computers/linux`)
- Configure DNS
- Configure Kerberos
- Configure the login manager, if necessary
- Configure PAM
- Configure SSSD

Supported distributions:

- Fedora
- RHEL 8/9 (and rebuilds: CentOS Stream, Rocky Linux, AlmaLinux, Oracle Linux)

## Differences to the Debian/Ubuntu version

| Debian/Ubuntu                             | RPM edition                                        |
|-------------------------------------------|----------------------------------------------------|
| `pam-auth-update`, `/usr/share/pam-configs` | `authselect` with a custom `ucs` profile (`with-mkhomedir`, `pam_group`) |
| `update-ca-certificates`                  | `update-ca-trust` (`/etc/pki/ca-trust/source/anchors`) |
| `/etc/ldap/ldap.conf`                     | `/etc/openldap/ldap.conf`                          |
| UDM computer type `computers/ubuntu`      | `computers/linux`                                  |
| `lsb_release`                             | `/etc/os-release`                                  |
| `ntpdate`                                 | `ntpdate` → `sntp` → `chronyd` (first one found)   |
| `/etc/X11/default-display-manager`        | `display-manager.service` systemd symlink          |
| resolvconf / dhclient DNS configuration   | NetworkManager (`nmcli`) or direct `/etc/resolv.conf` |

## Installation

### From the RPM package

Build the RPM and install it — all dependencies are pulled in automatically:

```
sudo dnf install rpm-build python3-devel python3-setuptools
python3 -m build --sdist .            # or: python3 setup.py sdist
rpmbuild -ta dist/univention-domain-join-cli-1.0.0.tar.gz
sudo dnf install ~/rpmbuild/RPMS/noarch/univention-domain-join-cli-1.0.0-1.*.noarch.rpm
```

### With pip

```
sudo dnf install python3-dns python3-ldap openssh-clients sshpass \
    openldap-clients sssd krb5-workstation authselect \
    oddjob-mkhomedir oddjob wget pip
sudo pip install .
```

## Usage

Run the tool as root and follow the prompts:

```
sudo univention-domain-join-cli
```

or, fully scripted:

```
sudo univention-domain-join-cli --dc-ip 10.0.0.1 --username Administrator --password-file /root/admin.pw
```

Run `univention-domain-join-cli --help` for all options. The command line
interface is compatible with the Debian/Ubuntu version, including
`--skip-login-manager`, `--force-ucs-dns`, `--domain` and `--dc-ip`.

Additionally, this port provides `--register-dns`: it registers an A record
(and, if a matching reverse zone exists, a PTR record) for the machine in
the UCS DNS zone. Registration only happens when the machine's primary IP
address is statically configured — DHCP clients are skipped, because a
record written at join time would go stale with the next lease.

The GUI of the original project was not ported — only the CLI is provided.

Before anything is changed, a backup of all modified configuration files is
created in `/var/univention-backup/<timestamp>_domain-join/`. The log file is
written to `/var/log/univention/domain-join-cli.log`.

## Notes

- Home directories for domain users are created via `pam_oddjob_mkhomedir`
  (authselect feature `with-mkhomedir`); the `oddjobd` service is enabled
  automatically.
- The authselect profile `custom/ucs` is created as a copy of the stock `sssd`
  profile, with `pam_group.so` added so that domain users are put into the
  local groups listed in `/etc/security/group.conf` at login time.
- The UCS root certificate is stored at `/etc/univention/ssl/ucsCA/CAcert.pem`
  (same path as on Ubuntu clients, referenced by `sssd.conf`) and additionally
  added to the system trust store.

## Documentation

Full documentation — architecture, join flow, files modified on the
client, CLI reference, dependencies and troubleshooting — is available in
[docs/DOCUMENTATION.md](docs/DOCUMENTATION.md).

## License

This project is derived from univention-domain-join and is licensed under the
AGPLv3, like the original. See `LICENSES/AGPL-3.0-only.txt`.
