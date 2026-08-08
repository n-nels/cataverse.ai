import neo4j, { Driver } from "neo4j-driver";

// Cached on `global` so Next.js dev-mode hot reloads reuse the same driver
// (and connection pool) instead of leaking a new one on every file edit.
const globalForNeo4j = global as unknown as { neo4jDriver?: Driver };

function createDriver(): Driver {
  const uri = process.env.NEO4J_URI;
  const username = process.env.NEO4J_USERNAME;
  const password = process.env.NEO4J_PASSWORD;

  if (!uri || !username || !password) {
    throw new Error(
      "Missing NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD env vars"
    );
  }

  return neo4j.driver(uri, neo4j.auth.basic(username, password), {
    // Return plain JS numbers instead of Neo4j's lossless Integer wrapper
    // ({ low, high }) — this dataset won't hit the >2^53 precision cliff
    // that feature guards against, and plain numbers serialize to JSON cleanly.
    disableLosslessIntegers: true,
  });
}

export const driver = globalForNeo4j.neo4jDriver ?? createDriver();

if (process.env.NODE_ENV !== "production") {
  globalForNeo4j.neo4jDriver = driver;
}
