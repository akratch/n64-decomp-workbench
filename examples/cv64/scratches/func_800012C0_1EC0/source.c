typedef struct ListNode {
    struct ListNode* previous;
    struct ListNode* next;
} ListNode;

void func_800012C0_1EC0(ListNode* left, ListNode* inserted) {
    ListNode* right = left->next;

    inserted->next = right;
    right->previous = inserted;
    left->next = inserted;
    inserted->previous = left;
}
