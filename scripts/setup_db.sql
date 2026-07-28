-- =====================================================
-- 1. ENABLE CHANGE TRACKING AT DATABASE LEVEL
-- =====================================================
ALTER DATABASE DEMOA
SET CHANGE_TRACKING = ON
(CHANGE_RETENTION = 7 DAYS, AUTO_CLEANUP = ON)
GO

-- =====================================================
-- 2. ENABLE CHANGE TRACKING ON EACH TABLE
-- =====================================================
ALTER TABLE saDocumentoVenta
ENABLE CHANGE_TRACKING
WITH (TRACK_COLUMNS_UPDATED = OFF)
GO

ALTER TABLE saFacturaVenta
ENABLE CHANGE_TRACKING
WITH (TRACK_COLUMNS_UPDATED = OFF)
GO

ALTER TABLE saFacturaVentaReng
ENABLE CHANGE_TRACKING
WITH (TRACK_COLUMNS_UPDATED = OFF)
GO

-- =====================================================
-- 3. CREATE SYNCHRONIZATION CONTROL TABLE
-- =====================================================
IF OBJECT_ID('dbo.SyncControl', 'U') IS NULL
BEGIN
    CREATE TABLE SyncControl (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        TableName NVARCHAR(128) NOT NULL,
        LastSyncVersion BIGINT NOT NULL DEFAULT 0,
        LastSyncDate DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
        SyncStatus NVARCHAR(50) NOT NULL DEFAULT 'PENDING',
        RecordsSynced INT DEFAULT 0,
        LastError NVARCHAR(MAX) NULL,
        CONSTRAINT UQ_SyncControl_TableName UNIQUE (TableName)
    )
END
GO

-- =====================================================
-- 4. CREATE PENDING OPERATIONS TABLE
-- =====================================================
IF OBJECT_ID('dbo.PendingOperations', 'U') IS NULL
BEGIN
    CREATE TABLE PendingOperations (
        Id BIGINT IDENTITY(1,1) PRIMARY KEY,
        TableName NVARCHAR(128) NOT NULL,
        RecordId NVARCHAR(100) NOT NULL,
        OperationType CHAR(1) NOT NULL,
        RecordData NVARCHAR(MAX) NULL,
        ChangeVersion BIGINT NOT NULL,
        CreatedDate DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
        RetryCount INT DEFAULT 0,
        LastError NVARCHAR(MAX) NULL,
        Status NVARCHAR(20) NOT NULL DEFAULT 'PENDING',
        CONSTRAINT CHK_OperationType CHECK (OperationType IN ('I', 'U', 'D'))
    )
END
GO

-- =====================================================
-- 5. CREATE PERFORMANCE INDEXES
-- =====================================================
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SyncControl_TableName')
    CREATE INDEX IX_SyncControl_TableName ON SyncControl(TableName)
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_PendingOperations_Status')
    CREATE INDEX IX_PendingOperations_Status ON PendingOperations(Status, CreatedDate)
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_PendingOperations_TableName')
    CREATE INDEX IX_PendingOperations_TableName ON PendingOperations(TableName, Status)
GO

-- =====================================================
-- 6. INSERT DIRECTIONAL INITIAL STATE RECORDS
-- =====================================================
MERGE SyncControl AS target
USING (
    SELECT 'saDocumentoVenta|LOCAL_TO_REMOTE' AS TableName UNION ALL
    SELECT 'saDocumentoVenta|REMOTE_TO_LOCAL' UNION ALL
    SELECT 'saFacturaVenta|LOCAL_TO_REMOTE' UNION ALL
    SELECT 'saFacturaVenta|REMOTE_TO_LOCAL' UNION ALL
    SELECT 'saFacturaVentaReng|LOCAL_TO_REMOTE' UNION ALL
    SELECT 'saFacturaVentaReng|REMOTE_TO_LOCAL'
) AS source
ON target.TableName = source.TableName
WHEN NOT MATCHED THEN
    INSERT (TableName, SyncStatus)
    VALUES (source.TableName, 'INITIALIZED');
GO