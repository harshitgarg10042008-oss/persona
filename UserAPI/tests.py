import importlib
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_institution(name='Test Uni', plan='Monthly', max_seats=None, domains=None):
    """Create an Institution and optionally register email domains."""
    from UserAPI.models import Institution, InstitutionDomain
    inst = Institution.objects.create(
        name=name,
        contact_email='admin@testuni.edu.in',
        plan=plan,
        max_seats=max_seats,
    )
    for d in (domains or []):
        InstitutionDomain.objects.create(institution=inst, domain=d)
    return inst


def _make_individual_user(email, password='StrongPass123!'):
    """Create a CustomUser + IndividualUser pair."""
    from UserAPI.models import IndividualUser
    user = User.objects.create_user(
        username=email, email=email, password=password
    )
    IndividualUser.objects.create(user=user, name='Test Student')
    return user


def _make_business_user(email, seat_cap=None):
    """Create a CustomUser + BusinessUser pair."""
    from UserAPI.models import BusinessUser
    user = User.objects.create_user(
        username=email, email=email, password='BizPass123!'
    )
    biz = BusinessUser.objects.create(
        user=user, name='Biz Admin', company_name='Test Corp', seat_cap=seat_cap
    )
    return biz


# ─────────────────────────────────────────────────────────────────────────────
# Existing auth session tests (preserved unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class AuthSessionTests(TestCase):
    def test_secret_key_is_persisted_between_reloads(self):
        from PersonaBackend import settings as settings_module

        secret_key_path = Path(settings_module.BASE_DIR) / '.secret_key'
        if secret_key_path.exists():
            secret_key_path.unlink()

        os.environ.pop('SECRET_KEY', None)

        reloaded_settings = importlib.reload(settings_module)
        first_key = reloaded_settings.SECRET_KEY

        reloaded_settings = importlib.reload(settings_module)
        second_key = reloaded_settings.SECRET_KEY

        self.assertEqual(first_key, second_key)
        self.assertTrue(secret_key_path.exists())

    def test_remember_me_sets_longer_session_expiry(self):
        user = User.objects.create_user(
            username='remember@example.com',
            email='remember@example.com',
            password='StrongPass123',
        )
        response = self.client.post(
            reverse('login'),
            {
                'username': 'remember@example.com',
                'password': 'StrongPass123',
                'remember_me': 'on',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertGreaterEqual(self.client.session.get_expiry_age(), 60 * 60 * 24 * 20)


# ─────────────────────────────────────────────────────────────────────────────
# Item 1 + 4: InstitutionDomain model
# ─────────────────────────────────────────────────────────────────────────────

class InstitutionDomainModelTests(TestCase):
    """Item 1 and 4: domain model stores multiple domains; normalises correctly."""

    def test_institution_can_have_multiple_domains(self):
        inst = _make_institution(domains=['xyz.edu.in', 'students.xyz.edu.in'])
        self.assertEqual(inst.allowed_domains.count(), 2)
        stored = set(inst.allowed_domains.values_list('domain', flat=True))
        self.assertIn('xyz.edu.in', stored)
        self.assertIn('students.xyz.edu.in', stored)

    def test_domain_normalised_to_lowercase_and_strips_at(self):
        from UserAPI.models import InstitutionDomain
        inst = _make_institution()
        d = InstitutionDomain.objects.create(institution=inst, domain='@UPPER.EDU.IN')
        self.assertEqual(d.domain, 'upper.edu.in')

    def test_institution_with_zero_domains_is_valid(self):
        """Item 6 — zero domains = code-only mode."""
        inst = _make_institution(domains=[])
        self.assertEqual(inst.allowed_domains.count(), 0)

    def test_duplicate_domain_raises_integrity_error(self):
        from UserAPI.models import InstitutionDomain
        from django.db import IntegrityError
        inst = _make_institution(domains=['xyz.edu.in'])
        with self.assertRaises(IntegrityError):
            InstitutionDomain.objects.create(institution=inst, domain='xyz.edu.in')


# ─────────────────────────────────────────────────────────────────────────────
# Item 2 + 3: IndividualSignUpForm — domain validation at signup
# ─────────────────────────────────────────────────────────────────────────────

class SignupFormDomainValidationTests(TestCase):
    """
    Test matrix:
      a) matching code + matching domain -> success
      b) matching code + non-matching domain -> clear rejection (names the domains)
      c) at seat cap -> capacity error (distinct from domain error)
      d) multi-domain: both domains pass, non-matching still blocked
      e) zero domains registered -> code-only mode, any email passes
      f) invalid code -> generic 'Invalid or inactive' message
    """

    BASE_DATA = {
        'name': 'Test Student',
        'password1': 'Tr0ub4dor&3',
        'password2': 'Tr0ub4dor&3',
        'user_type': 'individual',
    }

    def _form(self, email, code=''):
        from UserAPI.forms import IndividualSignUpForm
        data = {**self.BASE_DATA, 'email': email, 'institution_code': code}
        return IndividualSignUpForm(data)

    def test_a_matching_code_and_domain_succeeds(self):
        """(a) valid code + matching domain -> form valid."""
        inst = _make_institution(domains=['testuni.edu.in'])
        form = self._form('alice@testuni.edu.in', inst.code)
        self.assertTrue(form.is_valid(), msg=form.errors)

    def test_b_matching_code_wrong_domain_rejected_with_specific_error(self):
        """(b) valid code + wrong email -> error names institution AND required domains."""
        inst = _make_institution(name='XYZ University', domains=['xyzuniversity.edu.in'])
        form = self._form('alice@gmail.com', inst.code)
        self.assertFalse(form.is_valid())
        errors = form.errors.get('institution_code', [])
        self.assertTrue(
            any('XYZ University' in e for e in errors),
            msg=f"Expected institution name in error. Got: {errors}"
        )
        self.assertTrue(
            any('@xyzuniversity.edu.in' in e for e in errors),
            msg=f"Expected required domain in error. Got: {errors}"
        )
        # Must NOT say "Invalid or inactive" — that would mislead genuine students
        self.assertFalse(
            any('Invalid or inactive' in e for e in errors),
            msg=f"Should not say 'Invalid or inactive' for domain mismatch. Got: {errors}"
        )

    def test_c_seat_cap_shows_distinct_capacity_error(self):
        """(c) seat cap hit -> capacity error, not domain error."""
        inst = _make_institution(
            name='Capped Uni', domains=['cappeduni.edu.in'], max_seats=1
        )
        # Fill the one seat
        existing = User.objects.create_user(
            username='first@cappeduni.edu.in',
            email='first@cappeduni.edu.in',
            password='pass',
        )
        existing.institution = inst
        existing.is_active = True
        existing.save()

        form = self._form('second@cappeduni.edu.in', inst.code)
        self.assertFalse(form.is_valid())
        errors = form.errors.get('institution_code', [])
        self.assertTrue(
            any('seat limit' in e.lower() or 'capacity' in e.lower() for e in errors),
            msg=f"Expected capacity error. Got: {errors}"
        )
        # Must NOT mention domain — that's a different problem
        self.assertFalse(
            any('match' in e.lower() and 'email' in e.lower() for e in errors),
            msg=f"Capacity error should not mention domain mismatch. Got: {errors}"
        )

    def test_d_multi_domain_both_pass_non_matching_blocked(self):
        """(d) institution with 2 domains: each passes; outside domain blocked."""
        inst = _make_institution(
            name='Multi Uni', domains=['xyz.edu.in', 'students.xyz.edu.in']
        )
        form1 = self._form('alice@xyz.edu.in', inst.code)
        self.assertTrue(form1.is_valid(), msg=f"Domain 1 failed: {form1.errors}")

        form2 = self._form('bob@students.xyz.edu.in', inst.code)
        self.assertTrue(form2.is_valid(), msg=f"Domain 2 failed: {form2.errors}")

        form3 = self._form('eve@gmail.com', inst.code)
        self.assertFalse(form3.is_valid(), msg="Outside domain should be rejected")

    def test_e_zero_domains_allows_any_email(self):
        """(e) zero domains = code-only mode; any email domain passes."""
        inst = _make_institution(domains=[])
        form = self._form('alice@anydomain.com', inst.code)
        self.assertTrue(form.is_valid(), msg=form.errors)

    def test_f_invalid_code_gives_generic_error(self):
        """(f) completely wrong code -> 'Invalid or inactive' error."""
        form = self._form('alice@example.com', 'BADCODE1')
        self.assertFalse(form.is_valid())
        errors = form.errors.get('institution_code', [])
        self.assertTrue(
            any('Invalid or inactive' in e for e in errors),
            msg=f"Expected invalid code error. Got: {errors}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Item 5: join_institution view — domain + seat cap (INST-XXXXXX path)
# ─────────────────────────────────────────────────────────────────────────────

class JoinInstitutionValidationTests(TestCase):
    """
    Tests the join_institution view (BusinessUser INST-XXXXXX code path).
    The domain check resolves Institution via Institution.contact_email == business.user.email.
    """

    def setUp(self):
        from UserAPI.models import Institution, InstitutionDomain
        self.biz = _make_business_user('admin@testcorp.edu.in', seat_cap=None)
        self.institution = Institution.objects.create(
            name='Test Corp University',
            contact_email='admin@testcorp.edu.in',
            plan='Monthly',
        )
        InstitutionDomain.objects.create(
            institution=self.institution, domain='testcorp.edu.in'
        )
        self.student = _make_individual_user('student@testcorp.edu.in')

    def _join(self, user, code):
        self.client.force_login(user)
        return self.client.post(
            reverse('join_institution'),
            {'institution_code': code, 'consent_granted': 'on'},
            follow=True,
        )

    def _messages(self, resp):
        return [str(m) for m in resp.context['messages']]

    def test_matching_domain_join_succeeds(self):
        """Matching domain + valid code -> membership created."""
        from UserAPI.models import InstitutionMembership
        resp = self._join(self.student, self.biz.institution_code)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            InstitutionMembership.objects.filter(
                individual=self.student.individual_profile,
                business=self.biz, is_active=True
            ).exists()
        )

    def test_non_matching_domain_join_blocked(self):
        """Wrong email domain -> rejection with institution name + required domain in message."""
        from UserAPI.models import InstitutionMembership
        outsider = _make_individual_user('outsider@gmail.com')
        resp = self._join(outsider, self.biz.institution_code)
        msgs = self._messages(resp)
        self.assertTrue(
            any('Test Corp University' in m for m in msgs),
            msg=f"Expected institution name in error. Messages: {msgs}"
        )
        self.assertTrue(
            any('@testcorp.edu.in' in m for m in msgs),
            msg=f"Expected domain in error. Messages: {msgs}"
        )
        self.assertFalse(
            InstitutionMembership.objects.filter(
                individual=outsider.individual_profile, business=self.biz
            ).exists()
        )

    def test_seat_cap_on_join_path_distinct_from_domain_error(self):
        """seat_cap=1, cap full -> capacity error (not domain error)."""
        from UserAPI.models import InstitutionMembership
        from django.utils import timezone
        self.biz.seat_cap = 1
        self.biz.save()
        # Fill the seat
        InstitutionMembership.objects.create(
            individual=self.student.individual_profile,
            business=self.biz,
            consent_granted=True,
            consent_granted_at=timezone.now(),
            is_active=True,
        )
        second = _make_individual_user('second@testcorp.edu.in')
        resp = self._join(second, self.biz.institution_code)
        msgs = self._messages(resp)
        self.assertTrue(
            any('capacity' in m.lower() or 'seat' in m.lower() for m in msgs),
            msg=f"Expected capacity error. Messages: {msgs}"
        )
        self.assertFalse(
            any('email' in m.lower() and 'match' in m.lower() for m in msgs),
            msg=f"Capacity error should not mention email mismatch. Messages: {msgs}"
        )
        self.assertFalse(
            InstitutionMembership.objects.filter(
                individual=second.individual_profile, business=self.biz
            ).exists()
        )

    def test_no_domains_registered_allows_any_join(self):
        """Item 6 — business with zero domain rows: any email can join (code-only)."""
        from UserAPI.models import Institution, InstitutionMembership
        biz2 = _make_business_user('admin@nodomain.example', seat_cap=None)
        Institution.objects.create(
            name='No Domain Uni',
            contact_email='admin@nodomain.example',
            plan='Monthly',
        )
        student2 = _make_individual_user('anyone@randomdomain.com')
        resp = self._join(student2, biz2.institution_code)
        self.assertTrue(
            InstitutionMembership.objects.filter(
                individual=student2.individual_profile,
                business=biz2, is_active=True
            ).exists()
        )
