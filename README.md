<!--
SPDX-FileCopyrightText: 2017-2025 Univention GmbH
SPDX-License-Identifier: AGPL-3.0-only
-->
# Univention Domain Join

This is an assistant for joining [Ubuntu](https://ubuntu.com/about/release-cycle) and [Linux Mint](https://www.linuxmint.com/download_all.php) computers into Univention Corporate
Server (UCS) domains. It will perform the following steps for you:

- Create an LDAP object for your Ubuntu computer on UCS
- Configure DNS
- Configure Kerberos
- Configure the login manager, if necessary
- Configure PAM
- Configure SSSD

Univention Domain Join supports the following Linux distributions:

- `ubuntu24.04`
  - Ubuntu 24.04 LTS ("Noble Numbat")
- `ubuntu22.04`
  - Ubuntu 22.04 LTS („Jammy Jellyfish“)
  - Linux Mint 21 („Vanessa“)
- `ubuntu20.04`
  - Ubuntu 20.04 LTS („Focal Fossa“)
  - Linux Mint 20 („Ulyana“)
- `ubuntu18.04`
  - Ubuntu 18.04 LTS („Bionic Beaver“)
  - Linux Mint 19.2 („Tara“)
- `ubuntu17.10`
  - Ubuntu 17.10 („Artful Aardvark“)
- `ubuntu16.04`
  - Ubuntu 16.04 LTS („Xenial Xerus“)
- `ubuntu14.04`
  - Ubuntu 14.04 LTS („Trusty Tahr“)

The actual source code for the different Ubuntu releases can be found in
the corresponding git branches.

Univention Domain Join supports the Gnome and Unity desktop environments. The
configuration of the login manager of other desktop environments may not work,
but can be skipped using the `--skip-login-manager` parameter of the
`univention-domain-join-cli` tool.

# Download and Installation

Install the dependencies and the tool from source:

```shell
sudo apt update
sudo DEBIAN_FRONTEND=noninteractive apt install \
    python3-dnspython python3-ldap python3-netifaces python3-ipy python3-pip \
    openssh-client sshpass ldap-utils sssd sssd-ldap sssd-krb5 krb5-user wget -y
git clone https://github.com/mkomlaetou/univention-domain-join-deb.git
cd univention-domain-join-deb
sudo pip install --break-system-packages .
sudo ln -sf /usr/local/bin/univention-domain-join-cli /usr/bin/univention-domain-join-cli
```

`--break-system-packages` is needed on Debian 12 / Ubuntu 24.04 and newer
(PEP 668): pip otherwise refuses system-wide installs. It is safe here
because all Python dependencies (`python3-ldap`, `python3-dnspython`, …)
are installed via apt beforehand — pip only installs the tool itself into
`/usr/local`.

<!-- This installs the CLI as `/usr/local/bin/univention-domain-join-cli`, which
is not part of sudo's `secure_path` on Debian/Ubuntu — so
`sudo univention-domain-join-cli` would not be found. Either call it with
its full path, or add a symlink:

```shell
sudo ln -sf /usr/local/bin/univention-domain-join-cli /usr/bin/univention-domain-join-cli
``` -->

Run `sudo univention-domain-join-cli --help` for more details.

## Joining

```shell
# basic join (domain and DC are auto-detected via DNS)
sudo univention-domain-join-cli

# join against a specific DC
sudo univention-domain-join-cli --dc-ip 10.0.0.1

# join and register DNS records (static IP required, see below)
sudo univention-domain-join-cli --dc-ip 10.0.0.1 --register-dns
```

## DNS registration (`--register-dns`)

The join itself only creates the computer account in the UCS LDAP; no DNS
record is created for the machine. With `--register-dns`, the tool
additionally registers an A record in the domain's forward zone (and, if a
matching /24 reverse zone exists on the DC, a PTR record) on the machine's
computer object.

Registration only happens when the machine's primary IP address is
**statically configured** (NetworkManager `ipv4.method=manual`,
`iface <dev> inet static` in `/etc/network/interfaces`, or `dhcp4: false`
in netplan). DHCP clients are skipped, because a record written at join
time would go stale with the next lease.

## Granting sudo rights to domain groups

The CLI can grant sudo rights to UCS domain groups during the join by writing
a validated drop-in to `/etc/sudoers.d/50-ucs-domain-groups`:

```shell
# domain admins get sudo, but must re-authenticate with their password
sudo univention-domain-join-cli --sudo-groups "Domain Admins,IT-Support"

# passwordless sudo for automation accounts (use with care)
sudo univention-domain-join-cli --sudo-groups-nopasswd "Ansible Bots"
```

- `--sudo-groups` creates `%<group> ALL=(ALL:ALL) ALL` rules — sudo asks for
  the user's own password. This is the recommended variant for human
  administrators.
- `--sudo-groups-nopasswd` creates `%<group> ALL=(ALL:ALL) NOPASSWD: ALL`
  rules — sudo never asks for a password. Intended for automation and lab
  machines only; anyone in these groups can become root without any
  credential check.

Both options take a comma-separated list, can be combined in one join, and
group names with spaces are escaped automatically. The generated file is
validated with `visudo` before it is installed. The groups resolve through
SSSD at runtime, so no local group needs to exist.

## Leaving the domain (`--disjoin`)

To leave the domain again, use `--disjoin`: it deletes the machine's
computer object on the DC (including the DNS records created by
`--register-dns`), restores the pre-join configuration from the backup in
`/var/univention-backup/`, regenerates the PAM configuration without the
join's pam-configs profiles, removes the UCS root certificate and stops
SSSD. It asks for confirmation unless `--yes` is given.

```shell
sudo univention-domain-join-cli --disjoin --dc-ip 10.0.0.1

# only clean up this machine, keep the computer object on the DC
sudo univention-domain-join-cli --disjoin --local-only --yes
```

# Doc

Documentation on how to build and release this package to launchpad can be found [here](doc/dev.md)

# License

Univention Domain Join is built on top of many existing open source projects
which use their own licenses. The source code of all parts written by
Univention is licensed under the AGPLv3 . Please see the
[license file](./LICENSE) for more information.
