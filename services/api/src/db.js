import mysql from "mysql2/promise";

const baseConfig = {
  user: process.env.DB_USER ?? "flownote",
  password: process.env.DB_PASSWORD ?? "1234",
  database: process.env.DB_NAME ?? "flowNote",
  waitForConnections: true,
  connectionLimit: 10,
  namedPlaceholders: true,
  charset: "utf8mb4"
};

const connectionTarget = process.env.DB_HOST
  ? {
      host: process.env.DB_HOST,
      port: Number(process.env.DB_PORT ?? 3306)
    }
  : {
      socketPath: process.env.DB_SOCKET ?? "/tmp/mysql.sock"
    };

export const pool = mysql.createPool({
  ...baseConfig,
  ...connectionTarget
});

export async function pingDatabase() {
  const [rows] = await pool.query("SELECT DATABASE() AS database_name");
  return rows[0];
}
