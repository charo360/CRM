import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    Modal,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    Alert,
    ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { teamAPI } from '../context/api';

interface TeamMember {
    id: string;
    name: string;
    email: string;
    role: string;
    status: string;
    user_id?: string;
}

interface ConversationAssignmentPickerProps {
    visible: boolean;
    onClose: () => void;
    customerId: string;
    customerName: string;
    currentAssignee?: string | null;
    userId: string;
    onAssigned?: () => void;
}

export default function ConversationAssignmentPicker({
    visible,
    onClose,
    customerId,
    customerName,
    currentAssignee,
    userId,
    onAssigned,
}: ConversationAssignmentPickerProps) {
    const [members, setMembers] = useState<TeamMember[]>([]);
    const [loading, setLoading] = useState(false);
    const [assigning, setAssigning] = useState(false);

    useEffect(() => {
        if (visible) {
            fetchMembers();
        }
    }, [visible]);

    const fetchMembers = async () => {
        setLoading(true);
        try {
            const data = await teamAPI.getMembers();
            // Only show active members
            setMembers(data.filter((m: TeamMember) => m.status === 'active'));
        } catch (error) {
            console.error('Error fetching team members:', error);
            Alert.alert('Error', 'Failed to load team members');
        } finally {
            setLoading(false);
        }
    };

    const handleAssign = async (assigneeUserId: string | null, assigneeName: string) => {
        setAssigning(true);
        try {
            await teamAPI.assignConversation({
                customer_id: customerId,
                assigned_to: assigneeUserId,
                assigned_by: userId,
                notes: assigneeUserId ? `Assigned to ${assigneeName}` : 'Unassigned',
            });
            Alert.alert(
                'Success',
                assigneeUserId ? `Conversation assigned to ${assigneeName}` : 'Conversation unassigned'
            );
            onAssigned?.();
            onClose();
        } catch (error: any) {
            Alert.alert('Error', error.response?.data?.detail || 'Failed to assign conversation');
        } finally {
            setAssigning(false);
        }
    };

    return (
        <Modal visible={visible} animationType="slide" transparent={true} onRequestClose={onClose}>
            <View style={styles.overlay}>
                <View style={styles.container}>
                    <View style={styles.header}>
                        <Text style={styles.headerTitle}>Assign Conversation</Text>
                        <TouchableOpacity onPress={onClose}>
                            <Ionicons name="close" size={24} color="#FFFFFF" />
                        </TouchableOpacity>
                    </View>

                    <View style={styles.customerInfo}>
                        <Ionicons name="person-circle-outline" size={32} color="#25D366" />
                        <Text style={styles.customerName}>{customerName}</Text>
                    </View>

                    {loading ? (
                        <View style={styles.loadingContainer}>
                            <ActivityIndicator size="large" color="#25D366" />
                        </View>
                    ) : (
                        <ScrollView style={styles.membersList}>
                            {/* Unassign option */}
                            <TouchableOpacity
                                style={[
                                    styles.memberItem,
                                    !currentAssignee && styles.memberItemSelected,
                                ]}
                                onPress={() => handleAssign(null, 'Unassigned')}
                                disabled={assigning}
                            >
                                <View style={styles.memberInfo}>
                                    <View style={[styles.memberAvatar, { backgroundColor: '#556' }]}>
                                        <Ionicons name="remove-circle-outline" size={20} color="#FFF" />
                                    </View>
                                    <View style={styles.memberDetails}>
                                        <Text style={styles.memberName}>Unassigned</Text>
                                        <Text style={styles.memberRole}>Available to all team members</Text>
                                    </View>
                                </View>
                                {!currentAssignee && (
                                    <Ionicons name="checkmark-circle" size={24} color="#25D366" />
                                )}
                            </TouchableOpacity>

                            {/* Team members */}
                            {members.map((member) => {
                                const isAssigned = currentAssignee === member.user_id;
                                return (
                                    <TouchableOpacity
                                        key={member.id}
                                        style={[
                                            styles.memberItem,
                                            isAssigned && styles.memberItemSelected,
                                        ]}
                                        onPress={() => handleAssign(member.user_id || null, member.name)}
                                        disabled={assigning || !member.user_id}
                                    >
                                        <View style={styles.memberInfo}>
                                            <View
                                                style={[
                                                    styles.memberAvatar,
                                                    {
                                                        backgroundColor:
                                                            member.role === 'owner'
                                                                ? '#FFD700'
                                                                : member.role === 'manager'
                                                                ? '#4A90D9'
                                                                : '#25D366',
                                                    },
                                                ]}
                                            >
                                                <Text style={styles.memberInitial}>
                                                    {member.name.charAt(0).toUpperCase()}
                                                </Text>
                                            </View>
                                            <View style={styles.memberDetails}>
                                                <Text style={styles.memberName}>{member.name}</Text>
                                                <Text style={styles.memberRole}>
                                                    {member.role.charAt(0).toUpperCase() + member.role.slice(1)}
                                                    {member.status === 'invited' && ' (Invited)'}
                                                </Text>
                                            </View>
                                        </View>
                                        {isAssigned && (
                                            <Ionicons name="checkmark-circle" size={24} color="#25D366" />
                                        )}
                                    </TouchableOpacity>
                                );
                            })}

                            {members.length === 0 && (
                                <View style={styles.emptyContainer}>
                                    <Ionicons name="people-outline" size={48} color="#556" />
                                    <Text style={styles.emptyText}>No team members yet</Text>
                                    <Text style={styles.emptySubtext}>
                                        Add team members in Settings → Team Management
                                    </Text>
                                </View>
                            )}
                        </ScrollView>
                    )}
                </View>
            </View>
        </Modal>
    );
}

const styles = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        justifyContent: 'flex-end',
    },
    container: {
        backgroundColor: '#0A1628',
        borderTopLeftRadius: 20,
        borderTopRightRadius: 20,
        maxHeight: '80%',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 20,
        paddingVertical: 16,
        borderBottomWidth: 1,
        borderBottomColor: '#1A2942',
    },
    headerTitle: {
        fontSize: 18,
        fontWeight: '700',
        color: '#FFFFFF',
    },
    customerInfo: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 16,
        backgroundColor: '#1A2942',
        marginHorizontal: 16,
        marginTop: 16,
        borderRadius: 12,
        gap: 12,
    },
    customerName: {
        fontSize: 16,
        fontWeight: '600',
        color: '#FFFFFF',
        flex: 1,
    },
    loadingContainer: {
        padding: 40,
        alignItems: 'center',
    },
    membersList: {
        padding: 16,
    },
    memberItem: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: '#1A2942',
        padding: 16,
        borderRadius: 12,
        marginBottom: 8,
        borderWidth: 2,
        borderColor: 'transparent',
    },
    memberItemSelected: {
        borderColor: '#25D366',
        backgroundColor: '#25D36610',
    },
    memberInfo: {
        flexDirection: 'row',
        alignItems: 'center',
        flex: 1,
        gap: 12,
    },
    memberAvatar: {
        width: 40,
        height: 40,
        borderRadius: 20,
        alignItems: 'center',
        justifyContent: 'center',
    },
    memberInitial: {
        fontSize: 16,
        fontWeight: '700',
        color: '#FFFFFF',
    },
    memberDetails: {
        flex: 1,
    },
    memberName: {
        fontSize: 15,
        fontWeight: '600',
        color: '#FFFFFF',
        marginBottom: 2,
    },
    memberRole: {
        fontSize: 12,
        color: '#8899AA',
    },
    emptyContainer: {
        alignItems: 'center',
        paddingVertical: 40,
    },
    emptyText: {
        fontSize: 16,
        fontWeight: '600',
        color: '#8899AA',
        marginTop: 12,
    },
    emptySubtext: {
        fontSize: 13,
        color: '#556',
        marginTop: 6,
        textAlign: 'center',
        paddingHorizontal: 40,
    },
});
