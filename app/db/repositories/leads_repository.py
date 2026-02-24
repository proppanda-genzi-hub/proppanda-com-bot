from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base record UPSERT  (agent_id IS NULL — stores the user's personal lead data)
# Uses the partial unique index on (email) WHERE agent_id IS NULL
# ---------------------------------------------------------------------------
BASE_UPSERT_SQL = """
    INSERT INTO prop_panda_com_leads
        (email, name, phone, gender, nationality, profession, age_group,
         pass_type, session_id, last_target_table)
    VALUES
        (:email, :name, :phone, :gender, :nationality, :profession, :age_group,
         :pass_type, :session_id, :last_target_table)
    ON CONFLICT (email) WHERE agent_id IS NULL
    DO UPDATE SET
        {set_clause},
        updated_at = now()
"""

# ---------------------------------------------------------------------------
# Per-agent record UPSERT  (agent_id IS NOT NULL — one row per agent interest)
# Uses the partial unique index on (email, agent_id) WHERE agent_id IS NOT NULL
# Always overwrites conversation_summary with the fresh LLM-generated version.
# All personal fields use COALESCE so they are only set on the first insert and
# updated only when a non-null value arrives.
# ---------------------------------------------------------------------------
AGENT_INTERACTION_SQL = """
    INSERT INTO prop_panda_com_leads
        (email, name, phone, gender, nationality, profession, age_group,
         pass_type, agent_id, session_id, last_target_table, conversation_summary)
    VALUES
        (:email, :name, :phone, :gender, :nationality, :profession, :age_group,
         :pass_type, :agent_id, :session_id, :last_target_table, :conversation_summary)
    ON CONFLICT (email, agent_id) WHERE agent_id IS NOT NULL
    DO UPDATE SET
        name                 = COALESCE(EXCLUDED.name,              prop_panda_com_leads.name),
        phone                = COALESCE(EXCLUDED.phone,             prop_panda_com_leads.phone),
        gender               = COALESCE(EXCLUDED.gender,            prop_panda_com_leads.gender),
        nationality          = COALESCE(EXCLUDED.nationality,       prop_panda_com_leads.nationality),
        profession           = COALESCE(EXCLUDED.profession,        prop_panda_com_leads.profession),
        age_group            = COALESCE(EXCLUDED.age_group,         prop_panda_com_leads.age_group),
        pass_type            = COALESCE(EXCLUDED.pass_type,         prop_panda_com_leads.pass_type),
        session_id           = COALESCE(EXCLUDED.session_id,        prop_panda_com_leads.session_id),
        last_target_table    = COALESCE(EXCLUDED.last_target_table, prop_panda_com_leads.last_target_table),
        conversation_summary = EXCLUDED.conversation_summary,
        updated_at           = now()
"""


class LeadsRepository:
    """
    Repository for prop_panda_com_leads table operations.

    Record types:
    - Base record  (agent_id IS NULL):  one per email — stores personal lead data
      collected during the conversation (nationality, phone, pass_type, etc.)
    - Agent record (agent_id IS NOT NULL): one per (email, agent_id) pair — stores
      a per-agent conversation summary written for that listing agent.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # -----------------------------------------------------------------------
    # READ
    # -----------------------------------------------------------------------

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Fetch the base (agent_id IS NULL) record by email. Returns None if not found."""
        try:
            query = text("""
                SELECT id, email, name, phone, gender, nationality,
                       profession, age_group, pass_type, agent_id,
                       session_id, last_target_table, conversation_summary,
                       created_at, updated_at
                FROM prop_panda_com_leads
                WHERE email = :email AND agent_id IS NULL
                LIMIT 1
            """)
            result = await self.db.execute(query, {"email": email.lower().strip()})
            row = result.fetchone()
            return dict(row._mapping) if row else None
        except Exception as e:
            logger.error(f"LeadsRepository.get_by_email error: {e}")
            return None

    # -----------------------------------------------------------------------
    # WRITE — BASE RECORD (personal lead data, no agent linkage)
    # -----------------------------------------------------------------------

    async def upsert_lead(self, data: Dict[str, Any]) -> bool:
        """
        Insert or update the base lead record (agent_id = NULL) by email.
        This stores personal info collected at conversation start.
        agent_id is intentionally excluded — it belongs only in agent records.
        """
        email = (data.get("email") or "").lower().strip()
        if not email:
            return False

        field_map = ["name", "phone", "gender", "nationality", "profession",
                     "age_group", "pass_type", "session_id", "last_target_table"]

        params = {
            "email":            email,
            "name":             data.get("name"),
            "phone":            data.get("phone"),
            "gender":           data.get("gender"),
            "nationality":      data.get("nationality"),
            "profession":       data.get("profession"),
            "age_group":        data.get("age_group"),
            "pass_type":        data.get("pass_type"),
            "session_id":       data.get("session_id"),
            "last_target_table": data.get("last_target_table"),
        }

        set_parts = [f"{f} = :{f}" for f in field_map if params.get(f) is not None]
        if not set_parts:
            set_parts = ["session_id = :session_id"]

        sql = text(BASE_UPSERT_SQL.format(set_clause=", ".join(set_parts)))

        try:
            await self.db.execute(sql, params)
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"LeadsRepository.upsert_lead error: {e}")
            await self.db.rollback()
            return False

    async def update_fields(self, email: str, updates: Dict[str, Any]) -> bool:
        """
        Update specific fields on the BASE record (agent_id IS NULL) by email.
        Skips None values. Does NOT touch agent-specific records.
        """
        try:
            email = email.lower().strip()
            allowed = {"name", "phone", "gender", "nationality", "profession",
                       "age_group", "pass_type", "session_id", "last_target_table"}

            set_parts = []
            params = {"email": email}

            for key, val in updates.items():
                if key in allowed and val is not None:
                    set_parts.append(f"{key} = :{key}")
                    params[key] = val

            if not set_parts:
                return True

            set_clause = ", ".join(set_parts) + ", updated_at = now()"
            # Scope strictly to the base record — never touch agent rows
            query = text(
                f"UPDATE prop_panda_com_leads SET {set_clause} "
                f"WHERE email = :email AND agent_id IS NULL"
            )
            await self.db.execute(query, params)
            await self.db.commit()
            return True

        except Exception as e:
            logger.error(f"LeadsRepository.update_fields error: {e}")
            await self.db.rollback()
            return False

    # -----------------------------------------------------------------------
    # WRITE — AGENT RECORD (per-agent conversation summary)
    # -----------------------------------------------------------------------

    async def upsert_agent_interaction(
        self,
        email: str,
        agent_id: str,
        data: Dict[str, Any],
        conversation_summary: str,
    ) -> bool:
        """
        Insert or update a per-agent record in prop_panda_com_leads.

        - Key: (email, agent_id) — unique per agent per user.
        - INSERT on first enquiry to this agent's property.
        - UPDATE on subsequent enquiries — personal fields preserved via COALESCE,
          conversation_summary always overwritten with fresh LLM-generated value.
        - FK violation on agent_id (e.g. test agents) → logs warning, skips silently.
        """
        email = (email or "").lower().strip()
        if not email or not agent_id:
            return False

        filters = data.get("filters")
        params = {
            "email":                email,
            "name":                 data.get("name"),
            "phone":                (filters.tenant_phone        if filters else None) or data.get("phone"),
            "gender":               (filters.tenant_gender       if filters else None) or data.get("gender"),
            "nationality":          (filters.tenant_nationality  if filters else None) or data.get("nationality"),
            "profession":           (filters.tenant_profession   if filters else None) or data.get("profession"),
            "age_group":            (filters.tenant_age_group    if filters else None) or data.get("age_group"),
            "pass_type":            (filters.tenant_pass_type    if filters else None) or data.get("pass_type"),
            "agent_id":             agent_id,
            "session_id":           data.get("session_id"),
            "last_target_table":    data.get("last_target_table"),
            "conversation_summary": conversation_summary,
        }

        try:
            await self.db.execute(text(AGENT_INTERACTION_SQL), params)
            await self.db.commit()
            logger.info(f"✅ Agent interaction saved: email={email} agent={agent_id}")
            return True
        except IntegrityError as e:
            await self.db.rollback()
            if "foreign key" in str(e).lower() or "ForeignKeyViolation" in str(type(e).__name__):
                logger.warning(f"FK violation for agent_id={agent_id} — skipping agent record (test agent?)")
                return False
            logger.error(f"LeadsRepository.upsert_agent_interaction IntegrityError: {e}")
            return False
        except Exception as e:
            logger.error(f"LeadsRepository.upsert_agent_interaction error: {e}")
            await self.db.rollback()
            return False
