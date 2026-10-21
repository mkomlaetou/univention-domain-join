# univention-domain-join — RPM edition

Documentation for the RPM port of
[univention-domain-join](https://github.com/univention/univention-domain-join)
(`ubuntu24.04` branch).

## Overview

`univention-domain-join-cli` joins an RPM based Linux client into a
[Univention Corporate Server (UCS)](https://www.univention.com/products/ucs/)
domain. It creates a computer object for the client in the UCS directory
(UDM type `computers/linux`) and configures DNS, Kerberos, the OpenLDAP
client, SSSD, PAM and the graphical login manager so that domain users can
log in on the client.

Supported distributions (detected via `/etc/os-release`):

- Fedora
- RHEL 8/9 and rebuilds: CentOS Stream, Rocky Linux, AlmaLinux, Oracle Linux
- Amazon Linux

Only the CLI of the upstream project was ported — the GUI was not.

## Architecture

### Join flow

1. **CLI entry point** (`univention_domain_join/cli.py`,
   `univention-domain-join-cli`):
   - Parse command line arguments.
   - Pre-flight checks: must run as root (`check_if_run_as_root`),
     distribution must be supported (`/etc/os-release`,
     `utils/distributions.py`), required commands and Python modules must
     be installed (`check_dependencies`).
   - Discover the UCS domain automatically (`utils/domain.py`, via the
     `_domaincontroller_master._tcp.<domain>` DNS SRV record) unless
     `--domain`/`--dc-ip` are given; resolve the DC master's IP through
     DNS.
   - Ask for domain administrator credentials (unless
     `--username`/`--password`/`--password-file` are given) and verify SSH
     access to the DC with them.
   - Fetch all UCR (Univention Configuration Registry) variables from the
     DC by running `ucr shell` over SSH.
2. **Joiner** (`univention_domain_join/joiner.py`):
   - Check for conflicting configurations (unsupported login manager).
   - Back up every configuration file that will be modified to
     `/var/univention-backup/<timestamp>_domain-join/`.
   - Run the join steps in order (see below). Afterwards the temporary
     admin password file on the DC is always removed
     (`utils/ldap.py:cleanup_authentication`).
3. **Join steps** (`univention_domain_join/join_steps/`, one module per
   step, executed in this order):
   1. `dns_configurator.py` — only with `--force-ucs-dns`
   2. `ldap_configurator.py` (includes `root_certificate_provider.py`)
   3. `sssd_configurator.py`
   4. `pam_configurator.py`
   5. `login_manager_configurator.py` (unless `--skip-login-manager`)
   6. `kerberos_configurator.py`

All UDM/LDAP operations are executed **on the DC over SSH**
(`utils/ldap.py`, `utils/general.py:ssh`): the client has no local UDM
installation. The admin password is stored in a root-only file in
`/dev/shm` on the DC and used via `kinit --password-file` /
`udm --bindpwdfile`.

### What each join step configures

#### `dns_configurator.py` (only with `--force-ucs-dns`)

Points the client's DNS at the UCS DCs (from the UCR variables
`nameserver1..3`).

- With NetworkManager (the common case): sets `ipv4.dns`,
  `ipv4.ignore-auto-dns=yes` and `ipv4.dns-search` on every active
  connection via `nmcli` and brings the connections down/up.
- Without NetworkManager: writes `/etc/resolv.conf` directly.
- For `.local` domains: fixes the `mdns4_minimal`/`dns` ordering in
  `/etc/nsswitch.conf` so mDNS does not shadow regular DNS lookups.
- Verifies that the `_domaincontroller_master._tcp` SRV record resolves
  afterwards.

#### `ldap_configurator.py`

- Downloads the UCS root certificate (via `root_certificate_provider.py`).
- Creates a UDM computer object of type `computers/linux` for this client
  on the DC (or updates an existing entry of type
  `computers/linux`/`computers/ucc`/`computers/ubuntu`) with a random
  machine password and the client's OS name/version.
- Writes `/etc/openldap/ldap.conf` (RPM path; Debian uses
  `/etc/ldap/ldap.conf`) pointing at the DC's LDAP port 7389.
- Writes the machine account password to `/etc/machine.secret`
  (read-only for root).

#### `root_certificate_provider.py` (used by the LDAP and SSSD steps)

- Downloads `http://<dc>/ucs-root-ca.crt` to
  `/etc/univention/ssl/ucsCA/CAcert.pem` (same path as on Ubuntu clients,
  because `sssd.conf` and `ldap.conf` reference it there) using `wget` or
  `curl`.
- Copies it to `/etc/pki/ca-trust/source/anchors/UCSdomain.crt` and runs
  `update-ca-trust extract` (the RPM equivalent of Debian's
  `update-ca-certificates`).

#### `sssd_configurator.py`

- Writes `/etc/sssd/sssd.conf` (mode 0600): LDAP over the UCS port 7389 as
  the identity provider (binding with the machine account from
  `/etc/machine.secret`), Kerberos as the authentication provider.
  `krb5_kpasswd` points at the Samba DC if the joined DC runs Samba 4,
  otherwise at the UCS master.
- Enables and restarts the `sssd` service.

#### `pam_configurator.py`

- Appends a `pam_group` rule to `/etc/security/group.conf` so domain
  users become members of local desktop groups (`audio`, `cdrom`,
  `dialout`, `floppy`, `adm`, `video` — whichever exist) at login time.
- Creates the custom authselect profile `custom/ucs`
  (`/etc/authselect/custom/ucs/`) as a copy of the stock `sssd` profile,
  adds `pam_group.so` to its `system-auth`/`password-auth` stacks, and
  selects it with the `with-mkhomedir` feature. This replaces Debian's
  `pam-auth-update`/`/usr/share/pam-configs` mechanism.
- On old distributions without authselect (RHEL 7 era): falls back to
  `authconfig --enablesssd --enablesssdauth --enablemkhomedir --update`.
- Enables and starts `oddjobd` (needed by `pam_oddjob_mkhomedir` to
  actually create home directories).

#### `login_manager_configurator.py` (unless `--skip-login-manager`)

- Detects the active display manager through the
  `/etc/systemd/system/display-manager.service` symlink (Debian uses
  `/etc/X11/default-display-manager`). Headless systems and
  LightDM/GDM/SDDM are supported; anything else aborts the join.
- LightDM: writes
  `/etc/lightdm/lightdm.conf.d/99-show-manual-userlogin.conf` to show a
  manual login field and hide the local user list. GDM and SDDM accept
  arbitrary user names out of the box and need no changes.

#### `kerberos_configurator.py`

- Writes `/etc/krb5.conf` for the UCS realm (KDC and admin server are the
  joined DC; `kpasswd_server` is the Samba DC or the UCS master).
- Synchronizes the client's clock with the DC once (Kerberos tolerates at
  most 5 minutes of skew): tries `ntpdate`, then `sntp`, then `chronyd`.
  If chronyd is already running as a service, a one-shot `chronyd -q`
  would fail, so the running daemon is steered via `chronyc`
  (`add server`/`burst`/`makestep`) instead. A failed time sync only
  produces a warning — everything else is already configured at this
  point.

## Files written or modified on the client

Before anything is changed, all existing files listed below are backed up
to `/var/univention-backup/<timestamp>_domain-join/` (preserving their
relative paths).

| Path | Change |
|---|---|
| `/etc/sssd/sssd.conf` | Written (mode 0600) |
| `/etc/krb5.conf` | Written |
| `/etc/openldap/ldap.conf` | Written |
| `/etc/machine.secret` | Written (mode 0400) |
| `/etc/univention/ssl/ucsCA/CAcert.pem` | Downloaded UCS root CA |
| `/etc/pki/ca-trust/source/anchors/UCSdomain.crt` | Copy of the root CA; `update-ca-trust extract` is run |
| `/etc/security/group.conf` | Appended `pam_group` rule |
| `/etc/authselect/custom/ucs/*` | New authselect profile (copy of `sssd` + `pam_group.so`) |
| `/etc/pam.d/system-auth`, `/etc/pam.d/password-auth` | Rewritten by `authselect select` (backed up first) |
| `/etc/nsswitch.conf` | Rewritten by authselect; `mdns4_minimal` ordering fixed for `.local` domains |
| `/etc/resolv.conf` | Written directly, only with `--force-ucs-dns` and without NetworkManager |
| NetworkManager connection profiles | `ipv4.dns`/`ipv4.dns-search` modified via `nmcli`, only with `--force-ucs-dns` (no file backup — settings live in NM's profiles) |
| `/etc/lightdm/lightdm.conf.d/99-show-manual-userlogin.conf` | Written (LightDM only) |
| `/var/log/univention/domain-join-cli.log` | Log file (default; see `--logfile`) |
| `/var/univention-backup/<timestamp>_domain-join/` | Backup of all of the above |

On the DC, a UDM computer object `cn=<hostname>,cn=computers,<ldap_base>`
is created/updated, and a temporary password file
`/dev/shm/<username>domain-join` exists for the duration of the join.

## CLI reference

```
usage: univention-domain-join-cli [-h] [--version] [--username USERNAME]
                                  [--password PASSWORD] [--password-file FILE]
                                  [--skip-login-manager] [--domain DOMAIN]
                                  [--dc-ip IP] [--force-ucs-dns]
                                  [--logfile FILE]
```

| Option | Description |
|---|---|
| `--username USERNAME` | User name of a domain administrator. Asked interactively if omitted. |
| `--password PASSWORD` | Password of the domain administrator. Prefer `--password-file` in scripts — command line arguments are visible in the process list. |
| `--password-file FILE` | Path to a file containing only the administrator password. |
| `--skip-login-manager` | Do not configure the graphical login manager (also skips the conflict check for unsupported display managers). |
| `--domain DOMAIN` | UCS domain name. Can be left out if the domain is auto-detectable (client FQDN, reverse DNS or DNS server in the UCS domain). |
| `--dc-ip IP` | IP address of the UCS DC to join against. Skips domain/DC auto-detection entirely; use the DC master's IP if unsure. |
| `--force-ucs-dns` | Reconfigure the system's DNS to use the UCS DCs as nameservers. Default: keep the existing network settings (the client must then already be able to resolve the DC's and master's host names). |
| `--logfile FILE`, `-L FILE` | Log file path (default: `/var/log/univention/domain-join-cli.log`). |
| `--version` | Print the version and exit. |

### Examples

Interactive (asks for domain admin name and password, auto-detects the
domain):

```
sudo univention-domain-join-cli
```

Fully scripted, against a known DC, no login manager configuration:

```
sudo univention-domain-join-cli \
    --dc-ip 10.0.0.1 \
    --username Administrator \
    --password-file /root/admin.pw \
    --skip-login-manager
```

Scripted with explicit domain and DNS reconfiguration:

```
sudo univention-domain-join-cli \
    --domain example.com \
    --username Administrator \
    --password-file /root/admin.pw \
    --force-ucs-dns
```

The tool must be run as root.

## Dependencies

Install the dependencies from the distribution repositories:

```
sudo dnf install python3-dns python3-ldap openssh-clients sshpass \
    openldap-clients sssd krb5-workstation authselect \
    oddjob-mkhomedir oddjob wget pip
```

On RHEL and its rebuilds (Rocky, Alma, Oracle), `sshpass` is in the EPEL
repository, which has to be enabled first:

```
sudo dnf install epel-release
```

The CLI checks at startup that `ssh`, `sshpass`, `ldapsearch`,
`systemctl`, the Python modules `dns` and `ldap`, and `wget` or `curl`
are available, and prints a ready-to-use `dnf install` command if
anything is missing.

## Troubleshooting

**Log file.** Everything is logged to
`/var/log/univention/domain-join-cli.log` (or the path given with
`--logfile`). The log contains the full command output and tracebacks
that are not shown on stdout — always check it first.

**"It's not possible to connect to the UCS DC via ssh, with the given
credentials."** Typical causes:

- Wrong user name or password. The account must be a UCS domain
  administrator (e.g. `Administrator`).
- SSH is not reachable: check `ssh <username>@<dc-ip>` manually and that
  port 22 is open.
- The account is locked or its password expired.
- If password-less SSH (key authentication) works but the tool fails:
  the tool always uses password authentication via `sshpass`, so the
  password itself must be correct.

**"No DNS record for the DC master could be found."** The client cannot
resolve the `_domaincontroller_master._tcp.<domain>` SRV record. Either
make the UCS DC the DNS server of the client (manually or with
`--force-ucs-dns`), or skip auto-detection with `--dc-ip`.

**Time synchronization failed.** A warning at the end of the join means
the one-shot sync against the DC did not work. If `chronyd` is already
running as a service the tool uses `chronyc` automatically; otherwise
make sure one of `ntpdate`, `sntp` or `chronyd` is installed. Kerberos
logins fail if client and DC clocks differ by more than 5 minutes —
check with `date` against the DC and fix manually if needed.

**Verifying a successful join** (after a reboot):

```
# Domain users resolve via SSSD/NSS:
id <domainuser>
getent passwd <domainuser>

# Kerberos works:
kinit <domainuser>
klist

# SSSD is up and uses the new config:
systemctl status sssd
sssctl domain-list
```

**Rolling back.** Restore the files from the newest backup directory
`/var/univention-backup/<timestamp>_domain-join/` and run
`authselect select sssd with-mkhomedir --force` to switch PAM back to the
stock profile (or remove the `custom/ucs` profile). Then delete the
computer object on the DC with `udm computers/linux remove --dn
cn=<hostname>,cn=computers,<ldap_base>`.
