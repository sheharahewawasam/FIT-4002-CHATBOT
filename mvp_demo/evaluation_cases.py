evaluation_cases = [

    # =========================================================================
    # 1. sample-smsf-trust-deed.pdf — Ausis Super Fund
    # =========================================================================

    {
        "source": "sample-smsf-trust-deed.pdf",
        "fund_name": ["Ausis Super Fund"],
        "category": "Membership",
        "section_or_clause": "Clause 8 — Trustee may appoint additional members",
        "question":
            "What must a person do before the trustee may appoint them "
            "as an additional member of the fund?",

        "ground_truth_answer":
            "The person must complete and sign an Application to become "
            "a Member in a form approved by the trustee. The additional "
            "member must also consent to doing all things necessary to "
            "become a director of the trustee of the fund, unless they are "
            "unable to become a director under superannuation law.",

        "relevant_excerpts":
            ["""8 The trustee may appoint a person as an additional member
            of the fund if he or she has completed and signed an
            ‘Application to become a Member’ in a form approved by the
            trustee. The additional member must consent to doing all things
            necessary to become a director of the trustee of the fund upon
            appointment unless the additional member is unable to become
            a director of a trustee under superannuation law."""]
    },

    {
        "source": "sample-smsf-trust-deed.pdf",
        "fund_name": ["Ausis Super Fund"],
        "category": "Contributions",
        "section_or_clause": "Clauses 44–46 — Member, employer and other contributions",
        "question":
            "Does the deed allow downsizer and spouse contributions?",

        "ground_truth_answer":
            "Yes. Clause 44 allows a member, with the trustee's consent, "
            "to make contributions including downsizer contributions. "
            "Clause 46 also allows other persons, including a spouse, "
            "to make contributions with the consent of the trustee and member.",

        "relevant_excerpts":
            ["""44 With the trustee’s consent, a member may make any
            contributions (or procure that any contributions are made)
            to the fund that the member decides to, which includes downsizer
            contributions.""",

            """46 With the consent of the trustee and the member, any other
            person including:
            • a spouse of that member;
            • another member;
            • another trustee of a regulated superannuation fund (including
            pursuant to a contributions-split requested by the member's spouse);
            • any State, Territory or Federal government (including under the
            Federal government's co-contribution scheme) or authority;
            may make contributions to the fund in respect of that member."""]
    },

    {
        "source": "sample-smsf-trust-deed.pdf",
        "fund_name": ["Ausis Super Fund"],
        "category": "Investment",
        "section_or_clause": "Clause 58 — Forbidden investments",
        "question":
            "What investment restriction applies to loans to members "
            "or their relatives?",

        "ground_truth_answer":
            "The trustee must not make an investment in the form of a loan "
            "or other financial assistance to a member or a relative of a member.",

        "relevant_excerpts":
            ["""58 The trustee must not invest in any investment that is
            forbidden by superannuation law. The trustee must not make
            an investment in the form of a loan or other financial
            assistance to a member or a relative of a member."""]
    },

    {
        "source": "sample-smsf-trust-deed.pdf",
        "fund_name": ["Ausis Super Fund"],
        "category": "Death Benefits",
        "section_or_clause": "Clauses 91 and 95 — Death benefit payments and binding notices",
        "question":
            "What death-benefit arrangements are available under the deed?",

        "ground_truth_answer":
            "A death benefit may be dealt with under a death benefit "
            "agreement, a binding death benefit notice, or a non-binding "
            "death benefit notice. If a valid binding death benefit notice "
            "has been given, the trustee must comply with it subject to "
            "clauses 93 and 94.",

        "relevant_excerpts":
            ["""91 The trustee may pay the death benefit on the death of
            a current member of the fund. The trustee can do that under:
            91.1 a death benefit agreement, clause 93;
            91.2 a binding death benefit notice, clause 95; or
            91.3 a non-binding death benefit notice, clause 96.""",

            """95 After the death of a member or beneficiary who has given
            the trustee a binding death benefit notice, the trustee must
            comply with that notice subject to clauses 93 and 94."""]
    },


    # =========================================================================
    # 2. Trust_Deed_Sample_Superannuation_Fund.pdf
    # =========================================================================

    {
        "source": "Trust_Deed_Sample_Superannuation_Fund.pdf",
        "fund_name": ["Sample Superannuation Fund"],
        "category": "Trustee Appointment",
        "section_or_clause": "Rule 8 — Appointment, resignation and removal",
        "question":
            "Who has the right to appoint trustees or directors of a "
            "corporate trustee?",

        "ground_truth_answer":
            "The members have the right to appoint one or more trustees "
            "or directors of a corporate trustee. Where there is one member, "
            "the sole member may exercise that right. Otherwise, appointment "
            "may occur through a majority resolution at a meeting or a "
            "circular resolution signed by all members.",

        "relevant_excerpts":
            ["""The Members have the right to appoint one or more Trustees
            or Directors of a Corporate Trustee. The right to appoint a
            Trustee or Director of a Corporate Trustee may be exercised by:
            (i) a sole Member, where the Fund only has 1 Member; or
            (ii) a resolution passed by a majority of the Members present
            at a meeting called for the purpose or by circular resolution
            signed by all of the Members."""]
    },

    {
        "source": "Trust_Deed_Sample_Superannuation_Fund.pdf",
        "fund_name": ["Sample Superannuation Fund"],
        "category": "Death Benefits",
        "section_or_clause": "Rule 5.5 — Non-lapsing Binding Nomination",
        "question":
            "What requirements apply to a non-lapsing binding nomination?",

        "ground_truth_answer":
            "It must be in writing, signed and dated by the member in the "
            "presence of two witnesses who are at least 18 and are not named "
            "in the notice. The witnesses must sign a declaration that the "
            "member signed in their presence. The nomination does not lapse "
            "with time and may be revoked by written notice.",

        "relevant_excerpts":
            ["""A Non-lapsing Binding Nomination:
            (i) must be in writing;
            (ii) must be signed, and dated, by the Member in the presence
            of 2 witnesses, each of whom has turned 18 and neither of whom
            is a person mentioned in the notice;
            (iii) must contain a declaration signed, and dated, by the
            witnesses stating that the notice was signed by the Member
            in their presence;
            (iv) will not lapse by the passing of time;
            (v) may be revoked by the Member by written notice to the
            Trustee at any time."""]
    },

    {
        "source": "Trust_Deed_Sample_Superannuation_Fund.pdf",
        "fund_name": ["Sample Superannuation Fund"],
        "category": "Accounting and Audit",
        "section_or_clause": "Part 9 — Accounts, Audit, Records and Returns",
        "question":
            "How long must accounting records be retained, and must the "
            "accounts be audited?",

        "ground_truth_answer":
            "The accounting records must be kept in Australia for at least "
            "five years after the end of the relevant Year of Income. "
            "The trustee must appoint an Approved Auditor and ensure each "
            "set of accounts and statements is audited.",

        "relevant_excerpts":
            ["""(d) keep the accounting records of the Fund, or cause them
            to be kept, in Australia for at least 5 years after the end
            of the Year of Income to which they relate.""",

            """The Trustee must appoint, and has the power to dismiss, an
            Approved Auditor. The Trustee must ensure that each set of
            accounts and statements prepared in respect of a Year of
            Income is audited by the Auditor."""]
    },

    {
        "source": "Trust_Deed_Sample_Superannuation_Fund.pdf",
        "fund_name": ["Sample Superannuation Fund"],
        "category": "Governing Rules",
        "section_or_clause": "Rule 12 — Variation provision",
        "question":
            "What restrictions apply when the governing rules are amended?",

        "ground_truth_answer":
            "An amendment must not alter the fund's objects, improperly "
            "reduce member benefits, undermine equity between members, "
            "alter the specified WA or NSW property undertakings, or be "
            "contrary to or inconsistent with the Act and Regulations.",

        "relevant_excerpts":
            ["""Any amendment, revocation, replacement or modification
            must not:
            (a) alter the objects of the Fund;
            (b) reduce the benefits and entitlements payable to Members
            without the prior written approval of the Members unless the
            amendments are required to comply with the Relevant Law;
            (c) alter the rights and benefits of existing Members in any
            manner so that, on the whole, equity between Members is not
            maintained in accordance with their Member Benefit Account balances;
            (d) where the Fund holds Member-contributed WA Property and/or
            Member-contributed NSW Property, alter the undertakings
            contained in Rule 2.7 or 2.8; or
            (e) be contrary to or inconsistent with the Act and Regulations."""]
    },


    # =========================================================================
    # 3. SIS Act -1.pdf
    # =========================================================================

    {
        "source": "SIS Act -1.pdf",
        "fund_name": ["General"],
        "category": "Purpose of Legislation",
        "section_or_clause": "Section 3 — Object of Act",
        "question":
            "What is the main object of the Superannuation Industry "
            "(Supervision) Act 1993?",

        "ground_truth_answer":
            "The main object is to provide for the prudent management "
            "of certain superannuation funds, approved deposit funds and "
            "pooled superannuation trusts and for their supervision by "
            "APRA, ASIC and the Commissioner of Taxation.",

        "relevant_excerpts":
            ["""(1) The main object of this Act is to make provision for the
            prudent management of certain superannuation funds, approved
            deposit funds and pooled superannuation trusts and for their
            supervision by APRA, ASIC and the Commissioner of Taxation."""]
    },

    {
        "source": "SIS Act -1.pdf",
        "fund_name": ["General"],
        "category": "Regulatory Administration",
        "section_or_clause": "Section 6 — General administration of Act",
        "question":
            "Which regulator generally administers Parts 2A, 2B and 2C "
            "of the SIS Act?",

        "ground_truth_answer":
            "APRA generally administers Parts 2A, 2B and 2C, subject to "
            "the specified exceptions and to functions conferred on ASIC "
            "or the Commissioner of Taxation.",

        "relevant_excerpts":
            ["""6 General administration of Act

            (1) Subject to subsections (3) and (4):
            (a) APRA has the general administration of the following
            provisions, to the extent that administration of the provisions
            is not conferred on ASIC by paragraph (da) or the Commissioner
            of Taxation by paragraph (e), (ea), (fa), or (g):
            (i) Parts 2A, 2B and 2C (other than subsection 29SAA(3)
            and sections 29P to 29QC)."""]
    },

    {
        "source": "SIS Act -1.pdf",
        "fund_name": ["General"],
        "category": "SMSF Definition",
        "section_or_clause": "Section 17A — Definition of self managed superannuation fund",
        "question":
            "What are some basic requirements for a multi-member fund "
            "to be an SMSF under section 17A?",

        "ground_truth_answer":
            "The fund must have fewer than five members. If the trustees "
            "are individuals, each individual trustee must be a member. "
            "If the trustee is a body corporate, each director must be a "
            "member. Each member must also be a trustee or a director of "
            "the corporate trustee.",

        "relevant_excerpts":
            ["""(1) Subject to this section, a superannuation fund, other
            than a fund with only one member, is a self managed
            superannuation fund if and only if it satisfies the following
            conditions:
            (a) it has fewer than 5 members;""",

            """(b) if the trustees of the fund are individuals—each individual
            trustee of the fund is a member of the fund;
            (c) if the trustee of the fund is a body corporate—each director
            of the body corporate is a member of the fund;
            (d) each member of the fund:
            (i) is a trustee of the fund; or
            (ii) if the trustee of the fund is a body corporate—is a
            director of the body corporate."""]
    },

    {
        "source": "SIS Act -1.pdf",
        "fund_name": ["General"],
        "category": "Record Keeping",
        "section_or_clause": "Section 104 — Duty to keep records of changes of trustees",
        "question":
            "How long must records of changes in trustees and "
            "corporate-trustee directors be retained?",

        "ground_truth_answer":
            "Up-to-date records of trustee changes, changes of directors "
            "of corporate trustees, and section 118 consents must be kept "
            "and retained for at least 10 years.",

        "relevant_excerpts":
            ["""104 Duty to keep records of changes of trustees

            (1) Each trustee of a superannuation entity must ensure that
            up-to-date records of:
            (a) all changes of trustees of the entity; and
            (b) all changes of directors of any corporate trustee of the
            entity; and
            (c) all consents given under section 118;
            are kept and retained for at least 10 years."""]
    },


    # =========================================================================
    # 4. SIS Act Part 2-1.pdf
    # =========================================================================

    {
        "source": "SIS Act Part 2-1.pdf",
        "fund_name": ["General"],
        "category": "SMSF Auditor Registration",
        "section_or_clause": "Section 128B — Registration as an approved SMSF auditor",
        "question":
            "What requirements must an applicant satisfy to be registered "
            "as an approved SMSF auditor?",

        "ground_truth_answer":
            "The applicant must meet prescribed qualification and practical "
            "experience requirements, pass the competency examination, and "
            "satisfy the Regulator that they are capable of performing the "
            "duties, are unlikely to contravene auditor obligations, and "
            "are otherwise a fit and proper person.",

        "relevant_excerpts":
            ["""(1) The Regulator must grant an application under section 128A
            and register the applicant as an approved SMSF auditor if:
            (a) the applicant:
            (i) has the qualifications prescribed by the regulations; and
            (ii) has the practical experience prescribed by the regulations; and
            (iii) has passed a competency examination in accordance
            with section 128C; and
            (b) the Regulator is satisfied that the applicant:
            (i) is capable of performing the duties of an approved
            SMSF auditor; and
            (ii) is unlikely to contravene the obligations of an approved
            SMSF auditor under Subdivision B; and
            """,

            """(iii) is otherwise a fit and proper person to be an approved
            SMSF auditor."""]
    },

    {
        "source": "SIS Act Part 2-1.pdf",
        "fund_name": ["General"],
        "category": "SMSF Auditor Obligations",
        "section_or_clause": "Section 128F — Professional obligations of approved SMSF auditors",
        "question":
            "What professional obligations apply to an approved SMSF auditor?",

        "ground_truth_answer":
            "An approved SMSF auditor must complete required continuing "
            "professional development, hold prescribed professional indemnity "
            "insurance, comply with relevant competency and auditing standards, "
            "and comply with auditor independence requirements.",

        "relevant_excerpts":
            ["""128F Professional obligations of approved SMSF auditors

            An approved SMSF auditor must:
            (a) complete the continuing professional development
            requirements prescribed by the regulations; and
            (b) hold a current policy of professional indemnity insurance, of
            a level prescribed by the regulations, for claims that may be
            made against the auditor in connection with audits of self
            managed superannuation funds; and
            (c) comply with:
            (i) any competency standards that the Regulator determines
            under section 128Q; and
            (ii) any auditing standards, made by the Auditing and Assurance
            Standards Board under section 336 of the Corporations Act 2001,
            that are applicable to the duties of an approved SMSF auditor
            under this Act; and
            (iii) any auditing and assurance standards, formulated by the
            Auditing and Assurance Standards Board under section 227B of
            the Australian Securities and Investments Commission Act 2001,
            that are applicable to those duties; and
            (d) comply with the auditor independence requirements
            prescribed by the regulations."""]
    },

    {
        "source": "SIS Act Part 2-1.pdf",
        "fund_name": ["General"],
        "category": "APRA Powers",
        "section_or_clause": "Section 131D — APRA may give directions to an RSE licensee",
        "question":
            "Under what circumstances may APRA issue a direction to an "
            "RSE licensee?",

        "ground_truth_answer":
            "APRA may issue directions in circumstances including actual "
            "or likely contraventions, failure to meet a benchmark, the "
            "need to protect beneficiaries, inability to meet liabilities, "
            "material risks to assets, deterioration in financial condition, "
            "improper or financially unsound conduct, or risks to the "
            "Australian financial system.",

        "relevant_excerpts":
            ["""131D APRA may give directions to an RSE licensee in relation
            to licensee’s own conduct

            (1) APRA may give an RSE licensee a direction of a kind mentioned
            in subsection (2) if APRA has
            reason to believe that:
            (a) the RSE licensee has contravened a provision of:
            (i) this Act; or
            (ii) the regulations; or
            (iii) the prudential standards; or
            (iv) the Financial Sector (Collection of Data) Act 2001;""",

            """(b) the RSE licensee is likely to contravene a provision
            mentioned in paragraph (a), and the direction is reasonably
            necessary to deal with one or more prudential matters in
            relation to the RSE licensee;""",

            """(c) the RSE licensee has contravened a condition or direction
            under this Act or the Financial Sector (Collection of Data)
            Act 2001;""",

            """(ca) the RSE licensee, or the registrable superannuation entity
            of the RSE licensee, has failed to meet a benchmark that relates
            to the licensee or entity;""",

            """(d) the direction is necessary in the interests of beneficiaries
            of a registrable superannuation entity of the RSE licensee;""",

            """(e) the RSE licensee is, or is about to become, unable to meet
            its liabilities (whether as trustee of a registrable superannuation
            entity or otherwise);""",

            """(f) there is, or there might be, a material risk to the security
            of the assets of the RSE licensee (whether held as trustee of a
            registrable superannuation entity or otherwise);""",

            """(g) there has been, or there might be, a material deterioration
            in the financial condition of:""",

            """(i) the RSE licensee; or
            (ii) a registrable superannuation entity of which it is trustee;""",

            """(h) the RSE licensee is conducting:
            (i) its affairs; or
            (ii) the affairs of a registrable superannuation entity of
            which it is trustee;
            in an improper or financially unsound way;""",

            """(i) the failure to issue a direction would materially prejudice
            the interests or reasonable expectations of beneficiaries of a
            registrable superannuation entity of the RSE licensee;""",

            """(j) the RSE licensee is conducting:
            (i) its affairs; or
            (ii) the affairs of a registrable superannuation entity of
            which it is trustee;
            in a way that may cause or promote instability in the
            Australian financial system."""]
    },

    {
        "source": "SIS Act Part 2-1.pdf",
        "fund_name": ["General"],
        "category": "Trustee Regulation",
        "section_or_clause": "Section 133 — Suspension or removal of trustee",
        "question":
            "When may the Regulator suspend or remove a trustee of a "
            "superannuation entity?",

        "ground_truth_answer":
            "The Regulator may suspend or remove a trustee in circumstances "
            "including where the trustee is disqualified, where trustee "
            "conduct may make the financial position of the entity or another "
            "superannuation entity unsatisfactory, or where a trustee of a "
            "registrable superannuation entity is not an RSE licensee or "
            "member of a licensed group.",

        "relevant_excerpts":
            ["""(1) The Regulator may suspend or remove a trustee of a
            superannuation entity if:
            (a) either:
            (i) for a trustee who is an individual and who is a disqualified
            person only because he or she was disqualified under section 126H—
            the individual is disqualified from being or acting as a trustee
            of that superannuation entity; and
            (ii) otherwise—the trustee is a disqualified person within the
            meaning of Part 15; or
            (b) it appears to the Regulator that conduct that has been,
            is being, or is proposed to be, engaged in by the trustee or
            any other trustees of the entity may result in the financial
            position of the entity or of any other superannuation entity
            becoming unsatisfactory; or
            (c) if the trustee is a trustee of a registrable superannuation
            entity—the trustee is not an RSE licensee or a member of a
            group of individuals that is an RSE licensee."""]
    },


    # =========================================================================
    # 5. Super-changes-timeline-1.pdf
    # =========================================================================

    {
        "source": "Super-changes-timeline-1.pdf",
        "fund_name": ["General"],
        "category": "COVID-19 Relief Measures",
        "section_or_clause": "2020 — COVID-19 Superannuation Relief Measures",
        "question":
            "What three COVID-19 superannuation relief measures are listed "
            "for 2020?",

        "ground_truth_answer":
            "The three measures were temporary early release of up to "
            "$10,000 in each of the 2019/20 and 2020/21 financial years "
            "subject to conditions, a temporary halving of minimum pension "
            "drawdown amounts, and temporary relief from certain compliance "
            "requirements for related-party rental arrangements affected "
            "by COVID-19.",

        "relevant_excerpts":
            ["""Temporary early release of superannuation. Subject to meeting
            certain conditions and obtaining approval from the ATO in the form
            of a determination, members may
            access a single payment of up to $10,000 from their super in
            each of the 2019/20 and 2020/21 financial years. ATO released
            Super CRT Alert 004/2020 regarding early access processes;""",

            """Temporary reduction of the minimum pension drawdown amount.
            For account based pensions, transition to retirement income
            streams and market linked pensions,
            the minimum drawdown amount has been halved for both the
            2019/20 and 2020/21 financial years;""",

            """Temporary relief from certain compliance requirements
            regarding rental arrangements where an SMSF leases an asset
            to a related party, and that party has incurred financial
            difficulties as a result of COVID-19"""]
    },

    {
        "source": "Super-changes-timeline-1.pdf",
        "fund_name": ["General"],
        "category": "Investment Strategy",
        "section_or_clause": "2019 — SMSF Investment Strategies",
        "question":
            "What did the ATO do in 2019 about SMSFs with limited investment "
            "diversification?",

        "ground_truth_answer":
            "The ATO wrote to 17,700 SMSF trustees and auditors concerning "
            "limited diversification, reminding them to consider the risks. "
            "It later issued guidance on investment-strategy requirements.",

        "relevant_excerpts":
            ["""SMSF Investment Strategies

            ATO writes to 17,700 SMSF trustees, and auditors of those funds,
            regarding limited diversification of assets, reminding that they
            must have considered the risks of such limited diversification.
            ATO subsequently issued guidance as to requirements for
            investment strategies."""]
    },

    {
        "source": "Super-changes-timeline-1.pdf",
        "fund_name": ["General"],
        "category": "Contributions",
        "section_or_clause": "2018 — Downsizer Contributions & First Home Saver Contributions",
        "question":
            "When did downsizer contributions and First Home Saver "
            "contributions commence?",

        "ground_truth_answer":
            "They commenced on 1 July 2018.",

        "relevant_excerpts":
            ["""Downsizer Contributions & First Home Saver Contributions
            Commenced 1 July 2018."""]
    },

    {
        "source": "Super-changes-timeline-1.pdf",
        "fund_name": ["General"],
        "category": "Superannuation Reform",
        "section_or_clause": "2017 — Total Superannuation Balance Caps and Transfer Balance Caps",
        "question":
            "What effect did Total Superannuation Balance Caps and "
            "Transfer Balance Caps have in 2017?",

        "ground_truth_answer":
            "Total Superannuation Balance Caps affected a member's ability "
            "to make non-concessional and some other contributions in a "
            "particular year. Transfer Balance Caps limited the amount an "
            "individual could have in superannuation income streams, "
            "excluding Transition to Retirement Income Streams.",

        "relevant_excerpts":
            ["""Total Superannuation Balance Caps

            Introduced as part of the Superannuation Reform legislation,
            Total Superannuation Balance Caps impact the ability of a super
            fund member to make non-concessional and some other types of
            contributions to superannuation in a particular year.""",

            """Transfer Balance Caps

            Introduced as part of the Superannuation Reform legislation,
            Transfer Balance Caps limit the amount an individual may have
            in superannuation income streams (excluding Transition to
            Retirement Income Streams)."""]
    },
]
