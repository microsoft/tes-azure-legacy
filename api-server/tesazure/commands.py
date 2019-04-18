# coding: utf-8

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from faker import Faker
import click

from tesazure.database import db
from tesazure.user.models import User


@click.option('--num_users', default=5, help='Number of users.')
def populate_db(num_users):
    """Populates the database with seed data."""
    fake = Faker()
    users = []
    for _ in range(num_users):
        users.append(
            User(
                username=fake.user_name(),
                email=fake.email(),
                password=fake.word() + fake.word(),
                remote_addr=fake.ipv4()
            )
        )
    users.append(
        User(
            username='cburmeister',
            email='cburmeister@discogs.com',
            password='test123',
            remote_addr=fake.ipv4(),
            active=True,
            is_admin=True
        )
    )
    for user in users:
        db.session.add(user)
    db.session.commit()


def create_db():
    """Creates the database."""
    db.create_all()


def drop_db():
    """Drops the database."""
    if click.confirm('Are you sure?', abort=True):
        db.drop_all()


def recreate_db():
    """Same as running drop_db() and create_db()."""
    drop_db()
    create_db()
