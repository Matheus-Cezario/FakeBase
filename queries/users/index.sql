-- GET Usuários ativos, com filtros opcionais
-- @param city = null
-- @param minAge int = 0
-- @param limit int = 20
SELECT name, email, age, address.city AS city
FROM users
WHERE active
  AND age >= :minAge
  AND (:city IS NULL OR address.city LIKE :city)
ORDER BY name
LIMIT :limit
