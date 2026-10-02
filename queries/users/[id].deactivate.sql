-- PUT Deactivate a user
-- @param id string
-- @one
UPDATE users SET active = false WHERE _id = :id
