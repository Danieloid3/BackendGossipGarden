-- Tabla para guardar los FCM tokens de los dispositivos del usuario.
-- Permite enviar push notifications cuando la app está cerrada.
CREATE TABLE IF NOT EXISTS device_tokens (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token        TEXT        NOT NULL UNIQUE,
  platform     TEXT        CHECK (platform IN ('ios', 'android', 'web')),
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  last_used_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_device_tokens_user_id ON device_tokens(user_id);
