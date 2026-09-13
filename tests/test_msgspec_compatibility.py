# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from dataclasses import dataclass

from msgspec import Struct
from rxon.models import SkillInfo
from rxon.utils import to_dict

from holonode.worker import _create_dynamic_skill_object, fields, replace


class CustomStruct(Struct, frozen=True):
    id: str
    value: int


@dataclass(frozen=True)
class CustomDataclass:
    id: str
    value: int


def test_fields_compatibility():
    struct_fields = fields(CustomStruct)
    assert len(struct_fields) == 2
    assert {f.name for f in struct_fields} == {"id", "value"}

    struct_inst = CustomStruct(id="s1", value=42)
    struct_inst_fields = fields(struct_inst)
    assert len(struct_inst_fields) == 2
    assert {f.name for f in struct_inst_fields} == {"id", "value"}

    dc_class_fields = fields(CustomDataclass)
    assert len(dc_class_fields) == 2
    assert {f.name for f in dc_class_fields} == {"id", "value"}

    dc_inst = CustomDataclass(id="d1", value=24)
    dc_inst_fields = fields(dc_inst)
    assert len(dc_inst_fields) == 2
    assert {f.name for f in dc_inst_fields} == {"id", "value"}


def test_replace_compatibility():
    struct_inst = CustomStruct(id="s1", value=42)
    new_struct = replace(struct_inst, value=100)
    assert new_struct.id == "s1"
    assert new_struct.value == 100
    assert new_struct != struct_inst

    dc_inst = CustomDataclass(id="d1", value=24)
    new_dc = replace(dc_inst, value=200)
    assert new_dc.id == "d1"
    assert new_dc.value == 200
    assert new_dc != dc_inst


def test_create_dynamic_skill_object_msgspec():
    init_kwargs = {
        "name": "my_dynamic_skill",
        "type": "gpu",
        "custom_param": "hello",
        "another_param": 12345,
    }

    skill_obj = _create_dynamic_skill_object(SkillInfo, init_kwargs)

    assert isinstance(skill_obj, SkillInfo)
    assert skill_obj.name == "my_dynamic_skill"
    assert skill_obj.type == "gpu"
    assert skill_obj.custom_param == "hello"
    assert skill_obj.another_param == 12345

    serialized = to_dict(skill_obj)
    assert serialized["name"] == "my_dynamic_skill"
    assert serialized["type"] == "gpu"
    assert serialized["custom_param"] == "hello"
    assert serialized["another_param"] == 12345
