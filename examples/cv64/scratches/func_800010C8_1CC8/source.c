typedef struct PoolEntry {
    struct PoolEntry* next;
    void* value;
} PoolEntry;

extern PoolEntry D_80341060[];

PoolEntry* func_800010C8_1CC8(void* value) {
    PoolEntry* entry = D_80341060;

    do {
        if (entry->value == NULL) {
            entry->value = value;
            entry->next = NULL;
            return entry;
        }
        entry++;
    } while (entry < (PoolEntry*) objects_array);

    return NULL;
}
