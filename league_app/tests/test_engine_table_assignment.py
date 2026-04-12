"""Tests for league_app.engine.table_assignment — pure functions, no DB."""

from uuid import uuid4

from league_app.engine.table_assignment import (
    TableHistoryEntry,
    TableInfo,
    assign_tables,
)

T1, T2, T3 = uuid4(), uuid4(), uuid4()
P1, P2, P3, P4 = uuid4(), uuid4(), uuid4(), uuid4()
M1, M2 = uuid4(), uuid4()

TABLES = [
    TableInfo(uuid=T1, name="Table 1", number=1, table_type="bonzini", status="active"),
    TableInfo(uuid=T2, name="Table 2", number=2, table_type="tornado", status="active"),
    TableInfo(uuid=T3, name="Table 3", number=3, table_type="bonzini", status="active"),
]


class TestBasicAssignment:
    def test_assign_two_matches_to_two_tables(self):
        matches = [(M1, [P1, P2]), (M2, [P3, P4])]
        result = assign_tables(matches, TABLES[:2])
        assert len(result) == 2
        assert result[M1] != result[M2]

    def test_no_tables_available(self):
        matches = [(M1, [P1, P2])]
        result = assign_tables(matches, [])
        assert result == {}

    def test_more_matches_than_tables(self):
        m3 = uuid4()
        matches = [(M1, [P1, P2]), (M2, [P3, P4]), (m3, [P1, P3])]
        result = assign_tables(matches, TABLES[:2])
        assert len(result) == 2  # only 2 tables available

    def test_inactive_tables_excluded(self):
        inactive = TableInfo(uuid=uuid4(), name="Broken", number=4,
                            table_type="bonzini", status="inactive")
        matches = [(M1, [P1, P2])]
        result = assign_tables(matches, [inactive])
        assert result == {}


class TestRotation:
    def test_avoid_same_table_as_last_round(self):
        history = [
            TableHistoryEntry(participant_id=P1, table_uuid=T1,
                            table_type="bonzini", round_number=1),
            TableHistoryEntry(participant_id=P2, table_uuid=T1,
                            table_type="bonzini", round_number=1),
        ]
        matches = [(M1, [P1, P2])]
        result = assign_tables(matches, TABLES, history=history, rotate_tables=True)
        assert result[M1] != T1  # should avoid T1

    def test_prefer_unused_table_type(self):
        # P1 and P2 both played on bonzini twice, never on tornado
        history = [
            TableHistoryEntry(P1, T1, "bonzini", 1),
            TableHistoryEntry(P2, T1, "bonzini", 1),
            TableHistoryEntry(P1, T3, "bonzini", 2),
            TableHistoryEntry(P2, T3, "bonzini", 2),
        ]
        matches = [(M1, [P1, P2])]
        result = assign_tables(matches, TABLES, history=history, rotate_tables=True)
        # Should prefer T2 (tornado) over T1/T3 (bonzini)
        assert result[M1] == T2

    def test_rotation_disabled(self):
        history = [
            TableHistoryEntry(P1, T1, "bonzini", 1),
            TableHistoryEntry(P2, T1, "bonzini", 1),
        ]
        matches = [(M1, [P1, P2])]
        result = assign_tables(matches, TABLES, history=history, rotate_tables=False)
        # Without rotation, just picks first available
        assert result[M1] == T1


class TestFallback:
    def test_forced_repeat_when_only_one_table(self):
        history = [
            TableHistoryEntry(P1, T1, "bonzini", 1),
        ]
        matches = [(M1, [P1, P2])]
        result = assign_tables(matches, TABLES[:1], history=history, rotate_tables=True)
        # Only T1 available — must use it even though P1 played there
        assert result[M1] == T1
