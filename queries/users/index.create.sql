-- POST Cadastra um usuário (os campos que faltam são gerados pelo schematic)
INSERT INTO users (name, email, age) VALUES (:name, :email, :age)
