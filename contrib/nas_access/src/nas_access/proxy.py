"""
Proxy classes for resource allocators and object servers accessed via
DMZ file protocol.
"""

from __future__ import absolute_import

import logging

from openmdao.main.rbac import rbac

from .protocol import connect


class NAS_Allocator(object):
    """
    Allocator which uses :class:`NAS_Server` instead of :class:`ObjServer`
    when deploying.

    By adding the allocator to the resource allocation manager, resource
    requests will interrogate the allocator to see if it could be used. This
    would typically be done by :class:`ExternalCode` to execute a
    compute-intensive or parallel application.

    name: string
        Name of allocator, used in log messages, etc.

    dmz_host: string
        Name of intermediary file server.

    server_host: string
        Name of host to communicate with.

    Example resource configuration file entry::

        [Pleiades]
        classname: nas_access.NAS_Allocator
        dmz-host: dmzfs1
        server_host: pfe1

    """

    def __init__(self, name='NAS_Allocator', dmz_host=None, server_host=None):
        self._name = name
        self._servers = []
        self.dmz_host = dmz_host
        self.server_host = server_host
        if dmz_host and server_host:
            self.conn = connect(dmz_host, server_host, name)

    @property
    def name(self):
        """ Name of this allocator. """
        return self._name

    @rbac('*')
    def configure(self, cfg):
        """
        Configure allocator from :class:`ConfigParser` instance.
        Normally only called during manager initialization.

        cfg: :class:`ConfigParser`
            Configuration data is located under the section matching
            this allocator's `name`.

        Allows modifying 'dmz_host' and 'server_host'.
        """
        if cfg.has_option(self.name, 'dmz_host'):
            self.dmz_host = cfg.get(self.name, 'dmz_host')
        if cfg.has_option(self.name, 'server_host'):
            self.server_host = cfg.get(self.name, 'server_host')
        if self.dmz_host and self.server_host:
            self.conn = connect(self.dmz_host, self.server_host, self.name)

    @rbac('*')
    def max_servers(self, resource_desc):
        """
        Return the maximum number of servers which could be deployed for
        `resource_desc`.  The value needn't be exact, but performance may
        suffer if it overestimates.  The value is used to limit the number
        of concurrent evaluations.

        resource_desc: dict
            Description of required resources.
        """
        rdesc, info = self._check_local(resource_desc)
        if rdesc is None:
            return 0
        return self.conn.invoke('max_servers', resource_desc)

    @rbac('*')
    def time_estimate(self, resource_desc):
        """
        Return ``(estimate, criteria)`` indicating how well this resource
        allocator can satisfy the `resource_desc` request.  The estimate will
        be:

        - >0 for an estimate of walltime (seconds).
        -  0 for no estimate.
        - -1 for no resource at this time.
        - -2 for no support for `resource_desc`.

        The returned criteria is a dictionary containing information related
        to the estimate, such as hostnames, load averages, unsupported
        resources, etc.

        resource_desc: dict
            Description of required resources.
        """
        rdesc, info = self._check_local(resource_desc)
        if rdesc is None:
            return info
        return self.conn.invoke('time_estimate', resource_desc)

    def _check_local(self, resource_desc):
        """ Check locally-relevant resources. """
        rdesc = resource_desc.copy()
        for key in ('localhost', 'allocator'):
            if key not in rdesc:
                continue
            value = rdesc[key]
            if key == 'localhost':
                if value:
                    return None, (-2, {'localhost': 'requested local host'})
            if key == 'allocator':
                if value != self.name:
                    return None, (-2, {'allocator': 'wrong allocator'})
            del rdesc[key]
        return (rdesc, None)

    @rbac('*')
    def deploy(self, name, resource_desc, criteria):
        """
        Deploy a server suitable for `resource_desc`.
        Returns a proxy to the deployed server.

        name: string
            Name for server.

        resource_desc: dict
            Description of required resources.

        criteria: dict
            The dictionary returned by :meth:`time_estimate`.
        """
        name = name or 'sim-%d' % (len(self._servers) + 1)
        path = '%s/%s' % (self.name, name)
        self.conn.invoke('deploy', name, resource_desc, criteria, path)
        server = NAS_Server(self.dmz_host, self.server_host, path)
        self._servers.append(server)
        return server

    @rbac(('owner', 'user'))
    def release(self, server):
        """
        Shut-down `server`.

        server: :class:`NAS_Server`
            Server to be shut down.
        """
        if server in self._servers:
            self._servers.remove(server)
            server.shutdown()
        else:
            raise ValueError('No such server %r' % server)


class NAS_Server(object):
    """ Knows about executing a command via DMZ protocol. """

    def __init__(self, name, dmz_host, server_host, path):
        self.name = name
        self._logger = logging.getLogger(self.name)
        self.conn = connect(dmz_host, server_host, path)

    def shutdown(self):
        """ Shut-down this server. """
        self._logger.debug('shutdown')
        self.conn.send_request('shutdown')  # One-way.
        self.conn.close()

    @rbac('*')
    def echo(self, *args):
        """
        Simply return the arguments. This can be useful for latency/thruput
        masurements, connectivity testing, firewall keepalives, etc.
        """
        return self.conn.invoke('echo', *args)

    @rbac('owner')
    def execute_command(self, resource_desc):
        """
        Submit command based on `resource_desc`.

        resource_desc: dict
            Description of command and required resources.

        Forwards request via DMZ protocol and waits for reply.
        """
        try:
            job_name = resource_desc['job_name']
        except KeyError:
            job_name = ''
        command = resource_desc['remote_command']
        if 'args' in resource_desc:
            command = '%s %s' % (command, ' '.join(resource_desc['args']))
        self._logger.debug('execute_command %s %r', job_name, command)
        return self.conn.invoke('execute_command', resource_desc)

    @rbac('owner')
    def pack_zipfile(self, patterns, filename):
        """
        Create ZipFile of files matching `patterns` if `filename` is legal.

        patterns: list
            List of :mod:`glob`-style patterns.

        filename: string
            Name of ZipFile to create.
        """
        self._logger.debug('pack_zipfile %r', filename)
        return self.conn.invoke('pack_zipfile', patterns, filename)

    @rbac('owner')
    def unpack_zipfile(self, filename):
        """
        Unpack ZipFile `filename` if `filename` is legal.

        filename: string
            Name of ZipFile to unpack.
        """
        self._logger.debug('unpack_zipfile %r', filename)
        return self.conn.invoke('unpack_zipfile', filename)

    @rbac('owner')
    def chmod(self, path, mode):
        """
        Returns ``os.chmod(path, mode)`` if `path` is legal.

        path: string
            Path to file to modify.

        mode: int
            New mode bits (permissions).
        """
        self._logger.debug('chmod %r %o', path, mode)
        return self.conn.invoke('chmod', path, mode)

    @rbac('owner')
    def isdir(self, path):
        """
        Returns ``os.path.isdir(path)`` if `path` is legal.

        path: string
            Path to check.
        """
        self._logger.debug('isdir %r', path)
        return self.conn.invoke('isdir', path)

    @rbac('owner')
    def listdir(self, path):
        """
        Returns ``os.listdir(path)`` if `path` is legal.

        path: string
            Path to directory to list.
        """
        self._logger.debug('listdir %r', path)
        return self.conn.invoke('listdir', path)

    @rbac('owner')
    def open(self, filename, mode='r', bufsize=-1):
        """
        Returns ``open(filename, mode, bufsize)`` if `filename` is legal.

        filename: string
            Name of file to open.

        mode: string
            Accees mode.

        bufsize: int
            Size of buffer to use.
        """
        self._logger.debug('open %r %r %s', filename, mode, bufsize)
        raise NotImplementedError('open')

    @rbac('owner')
    def remove(self, path):
        """
        Remove `path` if `path` is legal.

        path: string
            Path to file to remove.
        """
        self._logger.debug('remove %r', path)
        return self.conn.invoke('remove', path)

    @rbac('owner')
    def stat(self, path):
        """
        Returns ``os.stat(path)`` if `path` is legal.

        path: string
            Path to file to interrogate.
        """
        self._logger.debug('stat %r', path)
        raise NotImplementedError('stat')

