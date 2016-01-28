# -*- coding: utf-8 -*-
"""Module for Application storage."""
from collections import namedtuple
from .idgenerators import UUIDGenerator
from .driver import PersistentDict
from ..utils import expand_and_format_path
from ..exceptions import DoesNotExistException, TooManyEntriesException
from .strategies import SaveStrategy, GetStrategy, DeleteStrategy
from .query import Query


# pylint: disable=too-few-public-methods
class InternalModelContructor(object):
    """Serializer raw data from storage to model.

    For internal use only.
    """

    def __init__(self, strategy):
        """Create new constructor."""
        self.strategy = strategy

    def __call__(self, raw_data, model_class):
        """Return barely wrapping raw_data with model_class."""
        return model_class(raw_data)


# pylint: disable=too-few-public-methods
class ModelContructor(InternalModelContructor):
    """Serializer raw data from storage to model."""

    def __call__(self, raw_data, model_class):
        """Call strategy to retrieve complete model tree."""
        model = super(ModelContructor, self).__call__(raw_data, model_class)
        return self.strategy.get(model)


Strategies = namedtuple('Strategies', ('getter', 'saver', 'deleter'))


class ApplicationStorage(object):
    """Storage for user data."""

    path = '~/.{application_name}.storage'
    defaultstorage = list

    def __init__(self, application_name, save_strategy=None,
                 get_strategy=None, delete_strategy=None, **kwargs):
        """Create new storage for application."""
        self._path = expand_and_format_path(
            [self.path], application_name=application_name, **kwargs
        )[0]
        self.driver = PersistentDict(self._path)
        self.id_generator = UUIDGenerator(self)

        self.strategies = Strategies(
            self.make_strategy(get_strategy, GetStrategy),
            self.make_strategy(save_strategy, SaveStrategy),
            self.make_strategy(delete_strategy, DeleteStrategy)
        )

        self.internal_model_constructor = InternalModelContructor(
            self.strategies.getter)
        self.model_constructor = ModelContructor(
            self.strategies.getter)

    def __enter__(self):
        """Start transaction."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Process transaction closing and sync driver."""
        self.driver.sync()

    def save(self, model):
        """Save model to storage.

        Will return model with id and saved mapped fields Model
        instances with ids.
        """
        model = self.strategies.saver.save(model)
        if getattr(model, model.id_name):
            saved_model = self.update(model)
        else:
            saved_model = self.create(model)
        return saved_model

    def create(self, model):
        """Add new model in it's list."""
        assert not getattr(model, model.id_name)
        model.id = self.generate_id(model)
        return self._internal_update(model)

    def update(self, model):
        """Update existed model in it's list."""
        identificator = getattr(model, model.id_name)
        assert identificator

        self._internal_delete(model)
        self.strategies.saver.mark_model(model)
        return self._internal_update(model)

    def delete(self, model):
        """Delete model from it's list."""
        self._internal_delete(model)
        self.strategies.deleter.delete(model)

    def confirm_delete(self, deleted_sets):
        """Remove intersection with deleted_sets from storage."""
        self.strategies.deleter.confirm_delete(deleted_sets)

    def get(self, model_class, query_union=None, **kwargs):
        """Get single model with passed lookups.

        Usage:
            list = storage.get(Model, any, **{'field.ge': 1, 'field.le': 5}
        """
        founded_models = self.filter(model_class, query_union, **kwargs)
        if not founded_models:
            raise DoesNotExistException
        elif len(founded_models) != 1:
            raise TooManyEntriesException
        return founded_models[0]

    def filter(self, model_class, query_union=None, **kwargs):
        """Filter model list with passed lookups.

        Usage:
            list = storage.filter(Model, any, **{'field.ge': 1, 'field.le': 5}
        """
        assert isinstance(model_class, type)
        assert kwargs
        query = Query(query_union, **kwargs)
        models = self.get_all(model_class)
        founded_models = [i for i in models if query(i)]
        return founded_models

    def get_all(self, model_class):
        """Retrieve full model list."""
        return self._get_all_base(model_class, self.model_constructor)

    def _internal_get_all(self, model_class):
        return self._get_all_base(model_class, self.internal_model_constructor)

    def _get_all_base(self, model_class, model_contructor):
        assert isinstance(model_class, type)
        name = model_class.set_name
        data = self.driver.setdefault(name, self.defaultstorage())
        models = self.defaultstorage(
            (model_contructor(i, model_class) for i in data)
        )
        return models

    def _internal_update(self, model):
        models = self._internal_get_all(type(model))
        models.append(model)
        self.driver[model.set_name] = models
        return model

    def _internal_delete(self, model):
        identificator = getattr(model, model.id_name)
        assert identificator

        models = self._internal_get_all(type(model))
        for index, model in enumerate(models):
            if model.id == identificator:
                models.pop(index)
                break
        self.driver[model.set_name] = models

    def low_get(self, key):
        """Get data directly from driver."""
        return self.driver[key]

    def low_set(self, key, value):
        """Set data directly to driver."""
        self.driver[key] = value

    def generate_id(self, model):
        """Generate new local id."""
        return self.id_generator(model)

    def make_strategy(self, strategy_class, default):
        """Create new strategy."""
        strategy_class = strategy_class or default
        return strategy_class(self)
