-- 经营数据同一门店同一日期只保留一条记录，重复导入通过 op_id 幂等更新。
CREATE UNIQUE INDEX IF NOT EXISTS uq_store_operations_store_date
    ON store_operations(store_id, record_date);
