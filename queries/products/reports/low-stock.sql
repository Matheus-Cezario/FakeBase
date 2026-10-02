-- GET Produtos com estoque baixo
-- @param below int = 10
SELECT code, name, stock FROM products WHERE stock < :below ORDER BY stock
