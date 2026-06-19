import crypto from "node:crypto";
import { pool } from "./db.js";

const SESSION_TTL_HOURS = 8;
const rolePriority = ["super-admin", "mes-user", "pop-user", "general-user"];

export const sessionCookieName = process.env.SESSION_COOKIE_NAME ?? "flownote_session";

function hashPassword(password, salt) {
  return crypto.createHash("sha256").update(`${salt}${password}`).digest("hex");
}

function parseCookies(cookieHeader = "") {
  return Object.fromEntries(
    cookieHeader
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const separatorIndex = part.indexOf("=");
        if (separatorIndex === -1) {
          return [part, ""];
        }
        return [
          decodeURIComponent(part.slice(0, separatorIndex)),
          decodeURIComponent(part.slice(separatorIndex + 1))
        ];
      })
  );
}

function toPublicUser(row) {
  const roles = row.roles ? row.roles.split(",").filter(Boolean) : [];
  const primaryRole = rolePriority.find((roleId) => roles.includes(roleId)) ?? "general-user";

  return {
    userId: row.user_id,
    loginId: row.login_id,
    displayName: row.display_name,
    roles,
    primaryRole
  };
}

export function isSuperAdmin(user) {
  return Boolean(user?.roles?.includes("super-admin"));
}

async function findUserByLoginId(loginId) {
  const [rows] = await pool.execute(
    `
      SELECT
        u.id,
        u.user_id,
        u.login_id,
        u.display_name,
        u.password_salt,
        u.password_hash,
        u.status,
        GROUP_CONCAT(r.role_id ORDER BY r.role_id SEPARATOR ',') AS roles
      FROM user_account u
      LEFT JOIN user_role ur ON ur.user_id = u.id
      LEFT JOIN role r ON r.id = ur.role_id
      WHERE u.login_id = :loginId
      GROUP BY u.id
      LIMIT 1
    `,
    { loginId }
  );

  return rows[0] ?? null;
}

async function findUserBySessionId(sessionId) {
  const [rows] = await pool.execute(
    `
      SELECT
        u.id,
        u.user_id,
        u.login_id,
        u.display_name,
        u.status,
        GROUP_CONCAT(r.role_id ORDER BY r.role_id SEPARATOR ',') AS roles
      FROM login_session s
      JOIN user_account u ON u.id = s.user_id
      LEFT JOIN user_role ur ON ur.user_id = u.id
      LEFT JOIN role r ON r.id = ur.role_id
      WHERE s.session_id = :sessionId
        AND s.revoked_at IS NULL
        AND s.expires_at > CURRENT_TIMESTAMP
      GROUP BY u.id
      LIMIT 1
    `,
    { sessionId }
  );

  if (!rows[0] || rows[0].status !== "ACTIVE") {
    return null;
  }

  await pool.execute(
    "UPDATE login_session SET last_seen_at = CURRENT_TIMESTAMP WHERE session_id = :sessionId",
    { sessionId }
  );

  return toPublicUser(rows[0]);
}

export function readSessionId(req) {
  const cookies = parseCookies(req.headers.cookie);
  return cookies[sessionCookieName] ?? null;
}

export function setSessionCookie(res, sessionId) {
  res.cookie(sessionCookieName, sessionId, {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    path: "/",
    maxAge: SESSION_TTL_HOURS * 60 * 60 * 1000
  });
}

export function clearSessionCookie(res) {
  res.clearCookie(sessionCookieName, {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    path: "/"
  });
}

export async function login(loginId, password) {
  const user = await findUserByLoginId(loginId);

  if (!user || user.status !== "ACTIVE") {
    return null;
  }

  const passwordHash = hashPassword(password, user.password_salt);

  if (passwordHash !== user.password_hash) {
    return null;
  }

  const sessionId = `sess_${crypto.randomUUID().replaceAll("-", "")}`;

  await pool.execute(
    `
      INSERT INTO login_session (session_id, user_id, expires_at)
      VALUES (
        :sessionId,
        :userId,
        DATE_ADD(CURRENT_TIMESTAMP, INTERVAL ${SESSION_TTL_HOURS} HOUR)
      )
    `,
    {
      sessionId,
      userId: user.id
    }
  );

  return {
    sessionId,
    user: toPublicUser(user)
  };
}

export async function currentUser(req) {
  const sessionId = readSessionId(req);

  if (!sessionId) {
    return null;
  }

  return findUserBySessionId(sessionId);
}

export async function logout(req) {
  const sessionId = readSessionId(req);

  if (!sessionId) {
    return;
  }

  await pool.execute(
    "UPDATE login_session SET revoked_at = CURRENT_TIMESTAMP WHERE session_id = :sessionId",
    { sessionId }
  );
}
