import pytest
from sqlalchemy import JSON
import sqlalchemy.dialects.postgresql as postgresql
from sqlalchemy.sql.elements import BinaryExpression, ColumnElement
from sqlalchemy.sql.operators import ColumnOperators

# Global monkeypatch for JSONB to JSON for SQLite compatibility in all tests
postgresql.JSONB = JSON

# To support .astext on SQLite during tests, we add it to the expression objects
def patch_astext():
    # Adding a property to ColumnOperators (which BinaryExpression inherits from)
    # to return the expression itself when .astext is accessed.
    # This works because on SQLite, standard JSON is just text/json, 
    # and the == operator works fine without explicit casting.
    
    @property
    def astext(self):
        return self
        
    ColumnOperators.astext = astext

patch_astext()
