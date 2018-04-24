# -*- coding: utf-8 -*-

# Copyright © 2018 Damir Jelić <poljar@termina.org.uk>
#
# Permission to use, copy, modify, and/or distribute this software for
# any purpose with or without fee is hereby granted, provided that the
# above copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
# RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF
# CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

from __future__ import unicode_literals

import click
import socket
import ssl
from logbook import Logger, StderrHandler
from client import Client, TransportType

click.disable_unicode_literals_warning = True


class CliClient(object):
    def __init__(self, user, password, host=None, port=None):
        self.host = host or "matrix.org"
        self.port = port or 443
        self.user = user
        self.password = password
        self.logger = Logger("matrix-cli")


def validate_host(ctx, param, value):
    try:
        host, _, port = value.partition(":")
        return (host, int(port) if port else 443)
    except ValueError:
        raise click.BadParameter("hosts need to be in format host:[port]")


@click.group()
@click.argument("host", callback=validate_host)
@click.argument("user")
@click.argument("password")
@click.option("--verbosity", type=click.Choice(["error", "warning", "info"]),
              default="error")
@click.pass_context
def cli(ctx, host, user, password, verbosity):
    StderrHandler(level=verbosity.upper()).push_application()
    ctx.obj = CliClient(user, password, host[0], host[1])


@cli.command()
@click.pass_obj
def sync(cli):
    sock, client = connect(cli.host, cli.port, cli.user)

    data = client.login(cli.password)
    sock.sendall(data)

    response = None

    while not response:
        received_data = sock.recv(4096)
        response = client.receive(received_data)

    data = client.sync()
    sock.sendall(data)
    response = None

    while not response:
        received_data = sock.recv(4096)
        response = client.receive(received_data)

    click.echo(response)

    disconnect(sock, client)

    return True

@cli.command()
@click.pass_obj
def login(cli):
    sock, client = connect(cli.host, cli.port, cli.user)

    data = client.login(cli.password)
    sock.sendall(data)

    response = None

    while not response:
        received_data = sock.recv(4096)
        response = client.receive(received_data)

    click.echo(response, err=True)
    click.echo(response.access_token)

    disconnect(sock, client)

    return True


def main():
    cli()


def disconnect(sock, client):
    data = client.disconnect()
    sock.sendall(data)

    sock.shutdown(socket.SHUT_RDWR)
    sock.close()


def connect(host, port, user=""):
    context = ssl.create_default_context()

    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.set_alpn_protocols(["h2", "http/1.1"])

    try:
        context.set_npn_protocols(["h2", "http/1.1"])
    except NotImplementedError:
        pass

    sock = socket.create_connection((host, port))
    ssl_socket = context.wrap_socket(sock, server_hostname=host)

    negotiated_protocol = ssl_socket.selected_alpn_protocol()
    if negotiated_protocol is None:
        negotiated_protocol = ssl_socket.selected_npn_protocol()

    transport_type = None

    if negotiated_protocol == "http/1.1":
        transport_type = TransportType.HTTP
    elif negotiated_protocol == "h2":
        transport_type = TransportType.HTTP2
    else:
        raise NotImplementedError

    client = Client(host, user)
    data = client.connect(transport_type)
    ssl_socket.sendall(data)

    return ssl_socket, client


if __name__ == "__main__":
    main()