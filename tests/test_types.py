# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from holonode.types import INVALID_INPUT_ERROR, PERMANENT_ERROR, TRANSIENT_ERROR


def test_types_constants():
    """Tests that the constants in the types module are defined correctly."""
    assert TRANSIENT_ERROR == "TRANSIENT_ERROR"
    assert PERMANENT_ERROR == "PERMANENT_ERROR"
    assert INVALID_INPUT_ERROR == "INVALID_INPUT_ERROR"
