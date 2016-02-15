# -*- coding: utf-8 -*-
"""Module for pull and push command."""
import abc
from base64 import b64decode
import six
from ..core.api import API
from ..core.commands import AbstractCommand
from ..core.models.terminal import (
    SshKey, Snippet,
    SshIdentity, SshConfig,
    Tag, Group,
    Host, PFRule,
    TagHost
)
from .client.controllers import ApiController
from .client.cryptor import RNCryptor
from ..core.storage.strategies import RelatedGetStrategy, SyncSaveStrategy


@six.add_metaclass(abc.ABCMeta)
class CloudSynchronizationCommand(AbstractCommand):
    """Base class for pull and push commands."""

    def extend_parser(self, parser):
        """Add more arguments to parser."""
        parser.add_argument(
            '-s', '--strategy', metavar='STRATEGY_NAME',
            help='Force to use specific strategy to merge data.'
        )
        parser.add_argument('-p', '--password', metavar='PASSWORD')
        return parser

    @abc.abstractmethod
    def process_sync(self, api_controller):
        """Do sync staff here."""
        pass

    def take_action(self, parsed_args):
        """Process CLI call."""
        encryption_salt = b64decode(self.config.get('User', 'salt'))
        hmac_salt = b64decode(self.config.get('User', 'hmac_salt'))
        password = parsed_args.password
        if password is None:
            password = self.prompt_password()
        self.validate_password(password)
        cryptor = RNCryptor()
        cryptor.password = password
        cryptor.encryption_salt = encryption_salt
        cryptor.hmac_salt = hmac_salt
        controller = ApiController(self.storage, self.config, cryptor)
        with self.storage:
            self.process_sync(controller)

    def validate_password(self, password):
        """Raise an error when password invalid."""
        username = self.config.get('User', 'username')
        API().login(username, password)


class PushCommand(CloudSynchronizationCommand):
    """Push data to Serverauditor cloud."""

    get_strategy = RelatedGetStrategy
    save_strategy = SyncSaveStrategy

    def process_sync(self, api_controller):
        """Push outdated local instances."""
        api_controller.post_bulk()
        self.log.info('Push data to Serverauditor cloud.')


class PullCommand(CloudSynchronizationCommand):
    """Pull data from Serverauditor cloud."""

    save_strategy = SyncSaveStrategy

    def process_sync(self, api_controller):
        """Pull updated remote instances."""
        api_controller.get_bulk()
        self.log.info('Pull data from Serverauditor cloud.')


class FullCleanCommand(CloudSynchronizationCommand):
    """Pull, delete all data and push to Serverauditor cloud."""

    get_strategy = RelatedGetStrategy
    save_strategy = SyncSaveStrategy

    supported_models = reversed((
        SshKey, Snippet,
        SshIdentity, SshConfig,
        Tag, Group,
        Host, PFRule,
        TagHost
    ))

    def process_sync(self, api_controller):
        """Pull updated remote instances."""
        api_controller.get_bulk()
        with self.storage:
            self.full_clean()
        api_controller.post_bulk()
        self.log.info('Full clean data from Serverauditor cloud.')

    def full_clean(self):
        """Remove all local and remote instances."""
        for model in self.supported_models:
            self.log.info('Start cleaning %s...', model)
            instances = self.storage.get_all(model)
            for i in instances:
                self.storage.delete(i)
            self.log.info('Complete cleaning')