"""Academic program feature regression tests."""

from datetime import date, timedelta

from app.models.student import Student
from app.services import program_service, report_service, section_service, student_service
from tests.conftest import csrf_from, login, make_section, make_student


class TestProgramSeed:
    def test_all_six_programs_seeded(self, db_session):
        program_service.seed_programs(db_session)
        programs = program_service.list_programs(db_session)
        assert [(p.code, p.name) for p in programs] == [
            ("BSCS", "BS CS"),
            ("BSCYB", "BS Cybersecurity"),
            ("BSCYB-3+2", "BS Cybersecurity 3+2"),
            ("BSEMC", "BS EMC"),
            ("BSIT-NA", "BS IT - Net Administration"),
            ("BSIT-WD", "BS IT - Web Dev"),
        ]
        assert all(p.is_active for p in programs)

    def test_seeding_is_idempotent(self, db_session):
        from app.models.program import Program

        first = program_service.seed_programs(db_session)
        second = program_service.seed_programs(db_session)
        assert len(first) == 6
        assert second == []
        assert db_session.query(Program).count() == 6

    def test_seeded_programs_appear_on_section_form(self, client, db_session, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        program_service.seed_programs(db_session)
        resp = client.get("/sections/new")
        assert resp.status_code == 200
        for code in ("BSIT-WD", "BSIT-NA", "BSCS", "BSEMC", "BSCYB", "BSCYB-3+2"):
            assert code in resp.text


class TestProgramSectionRelationships:
    def test_section_stores_program_relationship(self, db_session, seed_users, programs):
        section, errors = section_service.create_section(
            db_session,
            name="REL-1A",
            year_level=1,
            program_id=programs["BSCS"].id,
            created_by=seed_users["admin"].id,
        )
        assert errors == []
        assert section.program_id == programs["BSCS"].id
        assert section.program.code == "BSCS"

    def test_list_sections_filters_by_program(self, db_session, seed_users, programs):
        make_section(
            db_session, name="P1", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        make_section(
            db_session, name="P2", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSEMC"].id,
        )
        bsit_like = section_service.list_sections(db_session, program_id=programs["BSCS"].id)
        assert [s.name for s in bsit_like] == ["P1"]

    def test_same_name_allowed_across_programs_rejected_within_program(
        self, db_session, seed_users, programs
    ):
        ok, errors = section_service.create_section(
            db_session, name="TWIN", year_level=2,
            program_id=programs["BSCS"].id, created_by=seed_users["admin"].id,
        )
        assert errors == [] and ok is not None
        ok2, errors2 = section_service.create_section(
            db_session, name="TWIN", year_level=2,
            program_id=programs["BSEMC"].id, created_by=seed_users["admin"].id,
        )
        assert errors2 == [] and ok2 is not None
        dup, dup_errors = section_service.create_section(
            db_session, name="TWIN", year_level=2,
            program_id=programs["BSCS"].id, created_by=seed_users["admin"].id,
        )
        assert dup is None
        assert any("already exists" in e for e in dup_errors)

    def test_assignment_preserves_students(self, db_session, seed_users, programs):
        legacy = make_section(
            db_session, name="LEGACY-KEEP", year_level=1, created_by=seed_users["admin"].id
        )
        student = make_student(db_session, section_id=legacy.id, created_by=seed_users["admin"].id)
        updated, errors = section_service.update_section(
            db_session, legacy, name=legacy.name, year_level=1,
            program_id=programs["BSCYB-3+2"].id,
        )
        assert errors == []
        db_session.refresh(student)
        assert student.section_id == legacy.id
        assert student.section.program_id == programs["BSCYB-3+2"].id


class TestStudentProgramFilter:
    def test_filter_by_program(self, client, db_session, seed_users, programs):
        s_wd = make_section(
            db_session, name="F-WD", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSIT-WD"].id,
        )
        s_cs = make_section(
            db_session, name="F-CS", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        make_student(db_session, first_name="Web", last_name="Devone", section_id=s_wd.id, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Sci", last_name="Cseven", section_id=s_cs.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get(f"/students?program_id={programs['BSIT-WD'].id}")
        assert resp.status_code == 200
        assert "Devone" in resp.text
        assert "Cseven" not in resp.text
        assert "BSIT-WD" in resp.text  # Program column

    def test_blank_program_param_is_not_422(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?program_id=&year_level=&section_id=&q=")
        assert resp.status_code == 200

    def test_invalid_program_param_returns_400(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/students?program_id=abc")
        assert resp.status_code == 400
        assert "must be a positive integer" in resp.text

    def test_combined_program_year_section_filters(self, client, db_session, seed_users, programs):
        s1 = make_section(
            db_session, name="COMBO-1", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        s2 = make_section(
            db_session, name="COMBO-2", year_level=2, created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        s3 = make_section(
            db_session, name="COMBO-3", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSEMC"].id,
        )
        make_student(db_session, first_name="Hit", last_name="Combo", section_id=s1.id, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Miss1", last_name="Wrongyear", section_id=s2.id, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Miss2", last_name="Wrongprog", section_id=s3.id, created_by=seed_users["admin"].id)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get(
            f"/students?q=Combo&program_id={programs['BSCS'].id}&year_level=1&section_id={s1.id}"
        )
        assert resp.status_code == 200
        assert "Combo, Hit" in resp.text
        assert "Wrongyear" not in resp.text
        assert "Wrongprog" not in resp.text


class TestReportProgramFilters:
    def _seed(self, db_session, seed_users, programs):
        s_cs = make_section(
            db_session, name="R-CS", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        s_emc = make_section(
            db_session, name="R-EMC", year_level=2, created_by=seed_users["admin"].id,
            program_id=programs["BSEMC"].id,
        )
        a = make_student(db_session, first_name="Rep", last_name="Csone", section_id=s_cs.id, created_by=seed_users["admin"].id)
        b = make_student(db_session, first_name="Rep", last_name="Emcone", section_id=s_emc.id, created_by=seed_users["admin"].id)
        return a, b, s_cs, s_emc

    def test_combined_program_year_section_date_filters(self, client, db_session, seed_users, programs):
        a, b, s_cs, s_emc = self._seed(db_session, seed_users, programs)
        login(client, "admin@test.local", "admin-secret-pw-123")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        resp = client.get(
            f"/reports/result?date_from={yesterday}&date_to={tomorrow}"
            f"&program_id={programs['BSCS'].id}&year_level=1&section_id={s_cs.id}"
        )
        assert resp.status_code == 200
        assert "Csone" in resp.text
        assert "Emcone" not in resp.text

    def test_blank_report_filters_are_not_422(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get(
            "/reports/result?date_from=&date_to=&program_id=&year_level=&section_id=&group_by="
        )
        assert resp.status_code == 200

    def test_invalid_report_program_returns_400(self, client, seed_users):
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/result?program_id=not-a-number")
        assert resp.status_code == 400

    def test_csv_includes_program_column(self, client, db_session, seed_users, programs):
        self._seed(db_session, seed_users, programs)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/export.csv")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8-sig")
        assert "Program" in body.splitlines()[0]
        assert "BSCS" in body

    def test_totals_grouped_by_program(self, client, db_session, seed_users, programs):
        self._seed(db_session, seed_users, programs)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get("/reports/result?group_by=program")
        assert resp.status_code == 200
        assert "Totals by academic program" in resp.text
        assert "BSCS" in resp.text
        assert "BSEMC" in resp.text

    def test_printable_view_includes_program(self, client, db_session, seed_users, programs):
        self._seed(db_session, seed_users, programs)
        login(client, "admin@test.local", "admin-secret-pw-123")
        resp = client.get(f"/reports/print?program_id={programs['BSCS'].id}")
        assert resp.status_code == 200
        assert "BSCS" in resp.text
        assert "Emcone" not in resp.text


class TestDataPreservation:
    def test_seed_and_assignment_preserve_existing_data(self, client, db_session, seed_users, programs):
        legacy = make_section(
            db_session, name="PRESERVE", year_level=2, created_by=seed_users["admin"].id
        )
        student = make_student(
            db_session,
            first_name="Keep",
            last_name="Me",
            section_id=legacy.id,
            created_by=seed_users["admin"].id,
        )
        student.masterlist_student_number = "KEEP-1"
        db_session.commit()
        # Re-seed programs (idempotent) then assign the legacy section.
        program_service.seed_programs(db_session)
        _, errors = section_service.update_section(
            db_session, legacy, name=legacy.name, year_level=2,
            program_id=programs["BSIT-NA"].id,
        )
        assert errors == []
        db_session.expire_all()
        kept = db_session.get(Student, student.id)
        assert kept is not None
        assert kept.deleted_at is None
        assert kept.section_id == legacy.id
        assert kept.masterlist_student_number == "KEEP-1"
        assert kept.section.program.code == "BSIT-NA"

    def test_masterlist_lookup_still_works_with_programs(self, client, db_session, seed_users, programs):
        from app.models.masterlist import ImportBatch, StudentMasterlist

        batch = ImportBatch(file_name="compat.csv", imported_by=seed_users["admin"].id, total_rows=1, valid_rows=1)
        db_session.add(batch)
        db_session.flush()
        db_session.add(
            StudentMasterlist(
                student_number="PG-1", first_name="Lookup", last_name="Compat",
                import_batch_id=batch.id,
            )
        )
        db_session.commit()
        login(client, "facultya@test.local", "faculty-secret-pw-1")
        resp = client.get("/students/lookup?q=Compat")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["results"][0]["student_number"] == "PG-1"
        # Reservation created from lookup still works with program fields.
        section = make_section(
            db_session, name="LOOKUP-SEC", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        token = csrf_from(client, "/students/new")
        resp = client.post(
            "/students/new",
            data={
                "first_name": "Lookup",
                "last_name": "Compat",
                "section_id": str(section.id),
                "program_id": str(programs["BSCS"].id),
                "year_level": "1",
                "masterlist_student_number": "PG-1",
                "_csrf": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        student = db_session.query(Student).filter_by(masterlist_student_number="PG-1").one()
        assert student.section.program_id == programs["BSCS"].id


class TestServiceProgramCounts:
    def test_count_by_program_groups_filtered_set(self, db_session, seed_users, programs):
        s1 = make_section(
            db_session, name="CNT-1", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        s2 = make_section(
            db_session, name="CNT-2", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSCS"].id,
        )
        make_student(db_session, section_id=s1.id, created_by=seed_users["admin"].id)
        make_student(db_session, section_id=s2.id, created_by=seed_users["admin"].id)
        totals = report_service.count_by_program(
            db_session, date_from=None, date_to=None, year_level=None, section_id=None
        )
        assert ("BSCS", "BS CS", 2) in totals

    def test_list_students_program_filter_service(self, db_session, seed_users, programs):
        s1 = make_section(
            db_session, name="SVC-1", year_level=1, created_by=seed_users["admin"].id,
            program_id=programs["BSEMC"].id,
        )
        s2 = make_section(
            db_session, name="SVC-2", year_level=1, created_by=seed_users["admin"].id,
        )
        make_student(db_session, first_name="Prog", last_name="Yes", section_id=s1.id, created_by=seed_users["admin"].id)
        make_student(db_session, first_name="Prog", last_name="No", section_id=s2.id, created_by=seed_users["admin"].id)
        students, total = student_service.list_students(db_session, program_id=programs["BSEMC"].id)
        assert total == 1
        assert students[0].last_name == "Yes"
        # Unassigned-section students are excluded from every program filter.
        students, total = student_service.list_students(
            db_session, program_id=programs["BSCS"].id
        )
        assert total == 0
