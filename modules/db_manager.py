import json
import uuid
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import aiofiles
import aiosqlite  
import sqlite3 
from chainlit.element import Element, ElementDict
from chainlit.data.base import BaseDataLayer
from chainlit.data.storage_clients.base import BaseStorageClient
from chainlit.data.utils import queue_until_user_message
from chainlit.logger import logger
from chainlit.step import StepDict
from chainlit.types import (
    Feedback,
    FeedbackDict,
    PageInfo,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)
from chainlit.user import PersistedUser, User

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

class SQLiteDataLayer(BaseDataLayer):
    GHOST_STEPS = set()
    def __init__(
        self,
        storage_client: Optional[BaseStorageClient] = None,
        show_logger: bool = True,
        
    ):
        self.dir = os.path.join(os.getcwd(), ".chainlit_data")
        os.makedirs(self.dir, exist_ok=True)
    
        self.db_path = os.path.join(self.dir, "chat_history.sqlite")
        
        self.storage_client = storage_client
        self.show_logger = show_logger
        
        
        print(f"[DEBUG] 📂 Base de données : {self.db_path}")
        self._run_sync_init()

    async def get_current_timestamp(self) -> datetime:
        return datetime.now()

    def _run_sync_init(self):
        print("[DEBUG] 🔨 Initialisation synchrone des tables...")
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "User" (
                    "id" TEXT PRIMARY KEY,
                    "identifier" TEXT NOT NULL UNIQUE,
                    "metadata" TEXT,
                    "createdAt" TEXT,
                    "updatedAt" TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "Thread" (
                    "id" TEXT PRIMARY KEY,
                    "createdAt" TEXT,
                    "updatedAt" TEXT,
                    "deletedAt" TEXT,
                    "name" TEXT,
                    "userId" TEXT,
                    "userIdentifier" TEXT,
                    "tags" TEXT,
                    "metadata" TEXT,
                    FOREIGN KEY("userId") REFERENCES "User"("id")
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "Step" (
                    "id" TEXT PRIMARY KEY,
                    "name" TEXT,
                    "type" TEXT,
                    "threadId" TEXT,
                    "parentId" TEXT,
                    "input" TEXT,
                    "output" TEXT,
                    "metadata" TEXT,
                    "showInput" BOOLEAN,
                    "isError" BOOLEAN,
                    "createdAt" TEXT,
                    "startTime" TEXT,
                    "endTime" TEXT,
                    "generation" TEXT,
                    FOREIGN KEY("threadId") REFERENCES "Thread"("id")
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "Element" (
                    "id" TEXT PRIMARY KEY,
                    "threadId" TEXT,
                    "stepId" TEXT,
                    "type" TEXT,
                    "url" TEXT,
                    "chainlitKey" TEXT,
                    "name" TEXT,
                    "display" TEXT,
                    "objectKey" TEXT,
                    "size" TEXT,
                    "page" INTEGER,
                    "language" TEXT,
                    "mime" TEXT,
                    "props" TEXT,
                    "metadata" TEXT,
                    FOREIGN KEY("threadId") REFERENCES "Thread"("id"),
                    FOREIGN KEY("stepId") REFERENCES "Step"("id")
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "Feedback" (
                    "id" TEXT PRIMARY KEY,
                    "stepId" TEXT,
                    "value" REAL,
                    "comment" TEXT,
                    "name" TEXT,
                    FOREIGN KEY("stepId") REFERENCES "Step"("id")
                );
            """)
            conn.commit()
            conn.close()
            print("[DEBUG] ✅ Tables initialisées.")
        except Exception as e:
            print(f"[DEBUG] ❌ CRITICAL INIT ERROR: {e}")

    async def execute_query(
        self, query: str, params: Union[Dict, None] = None
    ) -> List[Dict[str, Any]]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                if params:
                    clean_params = {}
                    for k, v in params.items():
                        if isinstance(v, (dict, list)):
                            clean_params[k] = json.dumps(v)
                        elif isinstance(v, datetime):
                            clean_params[k] = v.isoformat()
                        else:
                            clean_params[k] = v
                    cursor = await db.execute(query, clean_params)
                else:
                    cursor = await db.execute(query)
                
                if query.strip().upper().startswith("SELECT") or "RETURNING" in query.upper():
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
                
                await db.commit()
                return []
        except Exception as e:
            logger.error(f"Database error: {e!s} | Query: {query}")
            print(f"[DEBUG] ❌ DB ERROR: {e} | Query: {query}")
            raise

    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        query = 'SELECT * FROM "User" WHERE identifier = :identifier'
        result = await self.execute_query(query, {"identifier": identifier})
        if not result:
            return None
        row = result[0]
        return PersistedUser(
            id=str(row.get("id")),
            identifier=str(row.get("identifier")),
            createdAt=row.get("createdAt"),
            metadata=json.loads(row.get("metadata") or "{}"),
        )

    async def create_user(self, user: User) -> Optional[PersistedUser]:
        # ID stable pour éviter les doublons au redémarrage
        user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, user.identifier))
        
        query = """
        INSERT INTO "User" (id, identifier, metadata, "createdAt", "updatedAt")
        VALUES (:id, :identifier, :metadata, :created_at, :updated_at)
        ON CONFLICT (identifier) DO UPDATE
        SET metadata = :metadata, "updatedAt" = :updated_at
        RETURNING *
        """
        now = await self.get_current_timestamp()
        params = {
            "id": user_id,
            "identifier": user.identifier,
            "metadata": json.dumps(user.metadata or {}),
            "created_at": now,
            "updated_at": now,
        }
        
        try:
            result = await self.execute_query(query, params)
            row = result[0]
            print(f"[DEBUG] ✅ User stable (UUID: {row.get('id')})")
            return PersistedUser(
                id=str(row.get("id")),
                identifier=str(row.get("identifier")),
                createdAt=row.get("createdAt"),
                metadata=json.loads(row.get("metadata") or "{}"),
            )
        except Exception:
            return PersistedUser(
                id=user_id, identifier=user.identifier, createdAt=str(now), metadata=user.metadata or {}
            )

    async def delete_feedback(self, feedback_id: str) -> bool:
        query = 'DELETE FROM "Feedback" WHERE id = :feedback_id'
        await self.execute_query(query, {"feedback_id": feedback_id})
        return True

    async def upsert_feedback(self, feedback: Feedback) -> str:
        query = """
        INSERT INTO "Feedback" (id, "stepId", name, value, comment)
        VALUES (:id, :step_id, :name, :value, :comment)
        ON CONFLICT (id) DO UPDATE
        SET value = :value, comment = :comment
        RETURNING id
        """
        feedback_id = feedback.id or str(uuid.uuid4())
        params = {
            "id": feedback_id,
            "step_id": feedback.forId,
            "name": "user_feedback",
            "value": float(feedback.value),
            "comment": feedback.comment,
        }
        results = await self.execute_query(query, params)
        return str(results[0]["id"])

    @queue_until_user_message()
    async def create_element(self, element: "Element"):
        if element.for_id in self.GHOST_STEPS:
            if self.show_logger:
                logger.info(f"[GHOST] 👻 Fichier ignoré car le parent {element.for_id} est un fantôme.")
            return
        if not element.for_id: return

        # Gestion des liens Thread/Step (Standard)
        if element.thread_id:
            query = 'SELECT id FROM "Thread" WHERE id = :thread_id'
            results = await self.execute_query(query, {"thread_id": element.thread_id})
            if not results: await self.update_thread(thread_id=element.thread_id)

        if element.for_id:
            query = 'SELECT id FROM "Step" WHERE id = :step_id'
            results = await self.execute_query(query, {"step_id": element.for_id})
            if not results:
                await self.create_step({
                    "id": element.for_id, "metadata": {}, "type": "run", 
                    "start_time": await self.get_current_timestamp(),
                    "end_time": await self.get_current_timestamp(),
                })

        # --- SAUVEGARDE PHYSIQUE LOCALE (PDF) ---
        # On définit où stocker le fichier sur le disque
        file_object_key = None
        
        # 1. Lecture du contenu
        content = None
        if element.path:
            async with aiofiles.open(element.path, "rb") as f: content = await f.read()
        elif element.content: content = element.content
        
        if content:
            # 2. Création du dossier 'files' dans 'reports'
            files_dir = os.path.join(self.dir, "files")
            os.makedirs(files_dir, exist_ok=True)
            
            # 3. Nom de fichier unique pour éviter les conflits
            clean_name = "".join([c for c in element.name if c.isalnum() or c in (' ', '.', '_')]).strip()
            file_name = f"{element.id}_{clean_name}"
            destination_path = os.path.join(files_dir, file_name)
            
            # 4. Écriture sur le disque
            async with aiofiles.open(destination_path, "wb") as f:
                await f.write(content)
            
            # 5. On stocke le chemin RELATIF dans la DB (compatible Docker/Exe)
            file_object_key = f"files/{file_name}"
            print(f"[DEBUG] 💾 Fichier sauvegardé : {destination_path}")

        # --- INSERTION EN BASE ---
        query = """
        INSERT INTO "Element" (
            id, "threadId", "stepId", metadata, mime, name, "objectKey", url,
            "chainlitKey", display, size, language, page, props
        ) VALUES (
            :id, :thread_id, :step_id, :metadata, :mime, :name, :object_key, :url,
            :chainlit_key, :display, :size, :language, :page, :props
        )
        ON CONFLICT (id) DO UPDATE SET props = EXCLUDED.props
        """
        params = {
            "id": element.id, "thread_id": element.thread_id, "step_id": element.for_id,
            "metadata": json.dumps({"size": element.size, "language": element.language, "display": element.display, "type": element.type, "page": getattr(element, "page", None)}),
            "mime": element.mime, "name": element.name, 
            "object_key": file_object_key, # <-- Chemin relatif stocké
            "url": element.url,
            "chainlit_key": element.chainlit_key, "display": element.display, "size": element.size,
            "language": element.language, "page": getattr(element, "page", None),
            "props": json.dumps(getattr(element, "props", {})),
        }
        await self.execute_query(query, params)

    async def get_element(self, thread_id: str, element_id: str) -> Optional[ElementDict]:
        query = 'SELECT * FROM "Element" WHERE id = :element_id AND "threadId" = :thread_id'
        results = await self.execute_query(query, {"element_id": element_id, "thread_id": thread_id})
        if not results: return None
        row = results[0]
        metadata = json.loads(row.get("metadata") or "{}")
        return ElementDict(
            id=str(row["id"]),
            threadId=str(row["threadId"]),
            type=metadata.get("type", "file"),
            url=str(row["url"]),
            name=str(row["name"]),
            mime=str(row["mime"]),
            objectKey=str(row["objectKey"]),
            forId=str(row["stepId"]),
            chainlitKey=row.get("chainlitKey"),
            display=row["display"],
            size=row["size"],
            language=row["language"],
            page=row["page"],
            autoPlay=row.get("autoPlay"),
            playerConfig=row.get("playerConfig"),
            props=json.loads(row.get("props") or "{}"),
        )

    @queue_until_user_message()
    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        # 1. Récupérer l'info du fichier avant de supprimer la ligne
        query = 'SELECT "objectKey" FROM "Element" WHERE id = :id'
        params = {"id": element_id}
        if thread_id:
            query += ' AND "threadId" = :thread_id'
            params["thread_id"] = thread_id
            
        results = await self.execute_query(query, params)
        
        # 2. Suppression Physique
        if results and results[0]["objectKey"]:
            await self._delete_physical_file(results[0]["objectKey"])

        # 3. Suppression SQL
        del_query = 'DELETE FROM "Element" WHERE id = :id'
        await self.execute_query(del_query, {"id": element_id})


    @queue_until_user_message()
    async def create_step(self, step_dict: StepDict):
        
        step_id = step_dict.get("id")

        # --- 1. LE REMPART (Mémoire) ---
        # Si cet ID est dans la liste des fantômes, on le bloque TOUT DE SUITE.
        # Même si metadata est vide cette fois-ci.
        if step_id in self.GHOST_STEPS:
            # On return silencieusement pour ne pas spammer les logs
            return

        # --- 2. L'ANALYSE (Premier passage) ---
        meta = step_dict.get("metadata", {})
        # Sécurité : Parfois meta est une string JSON
        if isinstance(meta, str):
            try: meta = json.loads(meta)
            except: meta = {}

        # Si on voit le drapeau pour la première fois...
        if meta and meta.get("disable_persistence") is True:
            if self.show_logger:
                logger.info(f"[GHOST] 👻 ID {step_id} détecté. Ajout à la Blacklist.")
            
            # ... ON L'AJOUTE À LA MÉMOIRE STATIQUE
            self.GHOST_STEPS.add(step_id)
            return
        
        # --- 2. GESTION THREAD/PARENT (Inchangé mais inclus pour cohérence) ---
        if step_dict.get("threadId"):
            thread_query = 'SELECT id FROM "Thread" WHERE id = :thread_id'
            thread_results = await self.execute_query(thread_query, {"thread_id": step_dict["threadId"]})
            if not thread_results:
                # Fix User ID (Admin fallback)
                user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "admin"))
                try:
                    from chainlit.context import context
                    if context.session and context.session.user:
                        user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, context.session.user.identifier))
                except: pass
                
                await self.update_thread(thread_id=step_dict["threadId"], user_id=user_id, name="Conversation")

        if step_dict.get("parentId"):
            parent_query = 'SELECT id FROM "Step" WHERE id = :parent_id'
            parent_results = await self.execute_query(parent_query, {"parent_id": step_dict["parentId"]})
            if not parent_results:
                await self.create_step({
                    "id": step_dict["parentId"], "metadata": {}, "type": "run", "createdAt": step_dict.get("createdAt"),
                })

        # --- 3. INSERTION (Query inchangée) ---
        query = """
        INSERT INTO "Step" (
            id, "threadId", "parentId", input, metadata, name, output,
            type, "startTime", "endTime", "showInput", "isError"
        ) VALUES (
            :id, :thread_id, :parent_id, :input, :metadata, :name, :output,
            :type, :start_time, :end_time, :show_input, :is_error
        )
        ON CONFLICT (id) DO UPDATE SET
            "parentId" = COALESCE(EXCLUDED."parentId", "Step"."parentId"),
            input = COALESCE(EXCLUDED.input, "Step".input),
            metadata = CASE WHEN EXCLUDED.metadata <> '{}' THEN EXCLUDED.metadata ELSE "Step".metadata END,
            name = COALESCE(EXCLUDED.name, "Step".name),
            output = COALESCE(EXCLUDED.output, "Step".output),
            type = CASE WHEN EXCLUDED.type = 'run' THEN "Step".type ELSE EXCLUDED.type END,
            "threadId" = COALESCE(EXCLUDED."threadId", "Step"."threadId"),
            "endTime" = COALESCE(EXCLUDED."endTime", "Step"."endTime"),
            "startTime" = MIN(EXCLUDED."startTime", "Step"."startTime"),
            "showInput" = COALESCE(EXCLUDED."showInput", "Step"."showInput"),
            "isError" = COALESCE(EXCLUDED."isError", "Step"."isError")
        """
        timestamp = await self.get_current_timestamp()
        created_at = step_dict.get("createdAt")
        if created_at: timestamp = datetime.strptime(created_at, ISO_FORMAT)

        params = {
            "id": step_dict["id"], "thread_id": step_dict.get("threadId"),
            "parent_id": step_dict.get("parentId"), "input": step_dict.get("input"),
            "metadata": json.dumps(step_dict.get("metadata", {})), "name": step_dict.get("name"),
            "output": step_dict.get("output"), "type": step_dict["type"],
            "start_time": timestamp, "end_time": timestamp,
            "show_input": 1 if step_dict.get("showInput") else 0,
            "is_error": 1 if step_dict.get("isError") else 0,
        }
        await self.execute_query(query, params)

    @queue_until_user_message()
    async def update_step(self, step_dict: StepDict):
        await self.create_step(step_dict)

    @queue_until_user_message()
    async def delete_step(self, step_id: str):
        # 1. Récupérer et supprimer tous les fichiers liés à cette étape (ex: images générées, pdfs)
        elem_query = 'SELECT "objectKey" FROM "Element" WHERE "stepId" = :id'
        elements = await self.execute_query(elem_query, {"id": step_id})
        
        for elem in elements:
            await self._delete_physical_file(elem["objectKey"])

        # 2. Nettoyage SQL en cascade (Feedback -> Element -> Step)
        await self.execute_query('DELETE FROM "Element" WHERE "stepId" = :id', {"id": step_id})
        await self.execute_query('DELETE FROM "Feedback" WHERE "stepId" = :id', {"id": step_id})
        await self.execute_query('DELETE FROM "Step" WHERE id = :id', {"id": step_id})

    # --- 3. FIX: SQLITE ALIAS FIX (Suppression radicale de 's') ---
    async def get_step(self, step_id: str) -> Optional[StepDict]:
        query = """
        SELECT  "Step".*,
                f.id as feedback_id,
                f.value as feedback_value,
                f."comment" as feedback_comment
        FROM "Step" 
        LEFT JOIN "Feedback" f ON "Step".id = f."stepId"
        WHERE "Step".id = :step_id
        """
        result = await self.execute_query(query, {"step_id": step_id})
        if not result:
            return None
        return self._convert_step_row_to_dict(result[0])

    async def get_thread_author(self, thread_id: str) -> str:
        # On fait un LEFT JOIN pour trouver le thread MÊME SI l'user est NULL
        query = """
        SELECT u.identifier
        FROM "Thread" t
        LEFT JOIN "User" u ON t."userId" = u.id
        WHERE t.id = :thread_id
        """
        results = await self.execute_query(query, {"thread_id": thread_id})
        
        if not results:
            # Le thread n'existe vraiment pas
            raise ValueError(f"Thread {thread_id} not found")
        
        identifier = results[0]["identifier"]
        
        # Si identifier est None (fil orphelin), on renvoie "admin" par défaut
        # Cela permet de supprimer les vieux fils buggés sans crash
        if not identifier:
            print(f"[DEBUG] ⚠️ Thread {thread_id} sans auteur. Fallback sur 'admin'.")
            return "admin"
            
        return identifier

    async def delete_thread(self, thread_id: str):
        print(f"[DEBUG] 🧹 Suppression complète du Thread {thread_id}...")
        
        # 1. Récupérer TOUS les fichiers associés au Thread
        elements_query = 'SELECT "objectKey" FROM "Element" WHERE "threadId" = :thread_id'
        elements_results = await self.execute_query(elements_query, {"thread_id": thread_id})
        
        # 2. Suppression Physique de tous les fichiers
        for elem in elements_results:
            await self._delete_physical_file(elem["objectKey"])
            
        # 3. Nettoyage SQL en cascade
        # D'abord les Feedbacks liés aux Steps du Thread
        # (SQLite ne gère pas toujours bien les JOIN dans les DELETE, on passe par une sous-requête ou on nettoie par stepId)
        steps_query = 'SELECT id FROM "Step" WHERE "threadId" = :thread_id'
        steps = await self.execute_query(steps_query, {"thread_id": thread_id})
        
        for step in steps:
            await self.execute_query('DELETE FROM "Feedback" WHERE "stepId" = :id', {"id": step["id"]})

        # Ensuite les Elements, Steps et le Thread lui-même
        await self.execute_query('DELETE FROM "Element" WHERE "threadId" = :thread_id', {"thread_id": thread_id})
        await self.execute_query('DELETE FROM "Step" WHERE "threadId" = :thread_id', {"thread_id": thread_id})
        await self.execute_query('DELETE FROM "Thread" WHERE id = :thread_id', {"thread_id": thread_id})
        
        print(f"[DEBUG] ✅ Thread {thread_id} et fichiers associés supprimés.")

    async def list_threads(self, pagination: Pagination, filters: ThreadFilter) -> PaginatedResponse[ThreadDict]:
        print(f"[DEBUG] 📑 list_threads. UserID filtre: {filters.userId}")
        query = """
        SELECT
            t.*,
            u.identifier as user_identifier,
            (SELECT COUNT(*) FROM "Thread" WHERE "userId" = t."userId") as total
        FROM "Thread" t
        LEFT JOIN "User" u ON t."userId" = u.id
        WHERE t."deletedAt" IS NULL
        """
        params: Dict[str, Any] = {}
        if filters.search:
            query += " AND t.name LIKE :search"
            params["search"] = f"%{filters.search}%"
        if filters.userId:
            query += ' AND t."userId" = :user_id'
            params["user_id"] = filters.userId
        if pagination.cursor:
            query += ' AND t."updatedAt" < (SELECT "updatedAt" FROM "Thread" WHERE id = :cursor)'
            params["cursor"] = pagination.cursor
        query += ' ORDER BY t."updatedAt" DESC LIMIT :limit'
        params["limit"] = pagination.first + 1

        results = await self.execute_query(query, params)
        print(f"[DEBUG] 🔢 Threads trouvés: {len(results)}")
        
        threads = results
        has_next_page = len(threads) > pagination.first
        if has_next_page: threads = threads[:-1]

        thread_dicts = []
        for thread in threads:
            thread_dicts.append(ThreadDict(
                id=str(thread["id"]),
                createdAt=thread["updatedAt"],
                name=thread["name"],
                userId=str(thread["userId"]) if thread["userId"] else None,
                userIdentifier=thread["user_identifier"],
                metadata=json.loads(thread["metadata"] or "{}"),
                steps=[], elements=[], tags=[],
            ))

        return PaginatedResponse(
            pageInfo=PageInfo(
                hasNextPage=has_next_page,
                startCursor=thread_dicts[0]["id"] if thread_dicts else None,
                endCursor=thread_dicts[-1]["id"] if thread_dicts else None,
            ),
            data=thread_dicts,
        )

    # --- 4. FIX: SQLITE ALIAS FIX DANS GET_THREAD ---
    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        query = """
        SELECT t.*, u.identifier as user_identifier
        FROM "Thread" t
        LEFT JOIN "User" u ON t."userId" = u.id
        WHERE t.id = :thread_id AND t."deletedAt" IS NULL
        """
        results = await self.execute_query(query, {"thread_id": thread_id})
        if not results: return None
        thread = results[0]

        steps_query = """
        SELECT  "Step".*, f.id as feedback_id, f.value as feedback_value, f."comment" as feedback_comment
        FROM "Step" 
        LEFT JOIN "Feedback" f ON "Step".id = f."stepId"
        WHERE "Step"."threadId" = :thread_id
        ORDER BY "Step"."startTime"
        """
        steps_results = await self.execute_query(steps_query, {"thread_id": thread_id})

        elements_query = 'SELECT * FROM "Element" WHERE "threadId" = :thread_id'
        elements_results = await self.execute_query(elements_query, {"thread_id": thread_id})

        if self.storage_client:
            for elem in elements_results:
                if not elem["url"] and elem["objectKey"]:
                    elem["url"] = await self.storage_client.get_read_url(object_key=elem["objectKey"])

        # FIX: Si le thread est orphelin (user_identifier est None), on dit qu'il est à "admin"
        # C'est ce qui débloque l'affichage dans l'interface
        user_identifier = thread["user_identifier"]
        if not user_identifier:
            user_identifier = "admin"

        return ThreadDict(
            id=str(thread["id"]), createdAt=thread["createdAt"], name=thread["name"],
            userId=str(thread["userId"]) if thread["userId"] else None,
            userIdentifier=user_identifier, # <-- Utilisation de la variable corrigée
            metadata=json.loads(thread["metadata"] or "{}"),
            steps=[self._convert_step_row_to_dict(step) for step in steps_results],
            elements=[self._convert_element_row_to_dict(elem) for elem in elements_results],
            tags=[],
        )

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        # 🚨 FIX ULTIME : Si aucun user_id n'est fourni (perte de session), on force l'Admin
        if not user_id:
            # On génère l'ID stable de l'admin (le même que dans create_user)
            user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "admin"))
            print(f"[DEBUG] 🛡️ update_thread: UserID manquant -> Force Admin ID: {user_id}")

        print(f"[DEBUG] 💾 update_thread {thread_id} pour UserID={user_id}")
        
        thread_name = truncate(
            name
            if name is not None
            else (metadata.get("name") if metadata and "name" in metadata else None)
        )

        if metadata is not None:
            existing = await self.execute_query(
                'SELECT "metadata" FROM "Thread" WHERE id = :thread_id',
                {"thread_id": thread_id},
            )
            base = {}
            if isinstance(existing, list) and existing:
                raw = existing[0].get("metadata") or {}
                if isinstance(raw, str):
                    try:
                        base = json.loads(raw)
                    except json.JSONDecodeError:
                        base = {}
                elif isinstance(raw, dict):
                    base = raw
            
            to_delete = {k for k, v in metadata.items() if v is None}
            incoming = {k: v for k, v in metadata.items() if v is not None}
            base = {k: v for k, v in base.items() if k not in to_delete}
            metadata = {**base, **incoming}

        now_str = datetime.now().isoformat()
        
        data = {
            "id": thread_id,
            "name": thread_name,
            "userId": user_id,
            "tags": json.dumps(tags) if tags else None,
            "metadata": json.dumps(metadata or {}),
            "updatedAt": now_str,
        }

        # Nettoyage des None sauf pour l'update partiel
        data = {k: v for k, v in data.items() if v is not None}

        columns = [f'"{k}"' for k in data.keys()]
        placeholders = [f":{k}" for k in data.keys()]
        
        update_sets = [f'"{k}" = EXCLUDED."{k}"' for k in data.keys() if k != "id"]

        if update_sets:
            query = f"""
                INSERT INTO "Thread" ({", ".join(columns)})
                VALUES ({", ".join(placeholders)})
                ON CONFLICT (id) DO UPDATE
                SET {", ".join(update_sets)};
            """
        else:
            query = f"""
                INSERT INTO "Thread" ({", ".join(columns)})
                VALUES ({", ".join(placeholders)})
                ON CONFLICT (id) DO NOTHING
            """

        await self.execute_query(query, data)

    async def get_favorite_steps(self, user_id: str) -> List[StepDict]:
        # 5. FIX: Alias fix ici aussi
        query = """
                SELECT "Step".*
                FROM "Step"
                JOIN "Thread" t ON "Step"."threadId" = t.id
                WHERE t."userId" = :user_id
                  AND json_extract("Step".metadata, '$.favorite') = true
                ORDER BY "Step"."createdAt" DESC
                """
        results = await self.execute_query(query, {"user_id": user_id})
        return [self._convert_step_row_to_dict(row) for row in results]

    def _extract_feedback_dict_from_step_row(self, row: Dict) -> Optional[FeedbackDict]:
        if row.get("feedback_id", None) is not None:
            return FeedbackDict(forId=row["id"], id=row["feedback_id"], value=row["feedback_value"], comment=row["feedback_comment"])
        return None

    def _convert_step_row_to_dict(self, row: Dict) -> StepDict:
        meta = json.loads(row.get("metadata") or "{}")
        # FIX: On récupère les actions stockées dans les métadonnées pour les renvoyer au front
        actions = meta.get("actions", [])
        
        return StepDict(
            id=str(row["id"]),
            threadId=str(row["threadId"]) if row.get("threadId") else "",
            parentId=str(row["parentId"]) if row.get("parentId") else None,
            name=str(row.get("name")),
            type=row["type"],
            input=row.get("input") or "",
            output=row.get("output") or "",
            metadata=meta,
            actions=actions, # <-- L'ajout critique pour les boutons
            createdAt=row["createdAt"],
            start=row["startTime"],
            showInput=bool(row.get("showInput")),
            isError=bool(row.get("isError")),
            end=row["endTime"],
            feedback=self._extract_feedback_dict_from_step_row(row),
        )

    def _convert_element_row_to_dict(self, row: Dict) -> ElementDict:
        metadata = json.loads(row.get("metadata") or "{}")
        
        # Reconstruction du chemin pour le frontend
        object_key = row.get("objectKey")
        path = None
        if object_key and not row.get("url"):
            # On reconstruit le chemin absolu à partir du dossier self.dir (reports)
            full_path = os.path.join(self.dir, object_key)
            if os.path.exists(full_path):
                path = full_path

        return ElementDict(
            id=str(row["id"]), threadId=str(row["threadId"]) if row.get("threadId") else None,
            type=metadata.get("type", "file"), url=row["url"], name=row["name"], mime=row["mime"],
            objectKey=object_key, 
            path=path, # <-- Chainlit servira ce fichier local
            forId=str(row["stepId"]), chainlitKey=row.get("chainlitKey"),
            display=row["display"], size=row["size"], language=row["language"], page=row["page"],
            autoPlay=row.get("autoPlay"), playerConfig=row.get("playerConfig"), props=json.loads(row.get("props") or "{}"),
        )

    async def build_debug_url(self) -> str: return ""
    async def cleanup(self): pass
    async def close(self) -> None:
        if self.storage_client: await self.storage_client.close()
        await self.cleanup()
    # Dans modules/db_manager.py

    async def get_thread_files(self, thread_id: str) -> List[ElementDict]:
        """Récupère tous les fichiers PDF associés à un thread."""
        query = """
        SELECT * FROM "Element" 
        WHERE "threadId" = :thread_id 
        AND (mime LIKE '%pdf%' OR name LIKE '%.pdf')
        """
        results = await self.execute_query(query, {"thread_id": thread_id})
        
        elements = []
        for row in results:
            # On utilise le helper existant pour reconstruire le chemin local
            elem_dict = self._convert_element_row_to_dict(row)
            # On vérifie que le fichier existe physiquement sur le disque
            if elem_dict.get("path") and os.path.exists(elem_dict["path"]):
                elements.append(elem_dict)
        
        return elements
    async def _delete_physical_file(self, object_key: str):
        """Supprime physiquement le fichier du disque ou du storage client."""
        if not object_key:
            return

        # 1. Cas Storage Client (S3, Azure Blob...)
        if self.storage_client:
            try:
                await self.storage_client.delete_file(object_key=object_key)
            except Exception as e:
                logger.warning(f"Erreur suppression cloud {object_key}: {e}")
        
        # 2. Cas Stockage Local (Par défaut)
        else:
            try:
                # On reconstruit le chemin absolu : .chainlit_data/files/mon_fichier.pdf
                full_path = os.path.join(self.dir, object_key)
                if os.path.exists(full_path):
                    os.remove(full_path)
                    print(f"[DEBUG] 🗑️ Fichier supprimé : {full_path}")
            except Exception as e:
                print(f"[DEBUG] ⚠️ Erreur suppression fichier local {object_key}: {e}")
def truncate(text: Optional[str], max_length: int = 255) -> Optional[str]:
    return None if text is None else text[:max_length]

