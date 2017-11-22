from django.contrib.auth.models import User, Group, Permission
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max, Min
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import Product, Unit, Seller, Order, Tag, Property, OrderUnit


class TagSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tag

    def to_representation(self, instance):
        return instance.name


class PropertySerializer(serializers.ModelSerializer):

    class Meta:
        model = Property

    def to_representation(self, instance):
        return {
            'name': instance.name,
            'values': [{
                'id': value.id,
                'value': value.value
            } for value in instance.propertyvalue_set.all()]
        }


class UnitSerializer(serializers.ModelSerializer):
    properties = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = ('sku', 'price', 'properties', 'images', 'num_in_stock')

    def get_properties(self, obj):
        return [{
                    'name': property_value.property.name,
                    'value': property_value.value
                } for property_value in obj.value_set.all()]

    def get_images(self, obj):
        images = obj.unitimage_set.all()

        if images.exists():
            return [image.image.url for image in images.all()]
        else:
            return []


class ProductListSerializer(serializers.ModelSerializer):
    tags = TagSerializer(
        many=True,
        read_only=True,
        source='tag_set'
    )
    prices = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ('id', 'title', 'tags', 'prices', 'image')

    def get_prices(self, obj):
        prices = obj.unit_set.aggregate(max=Max('price'), min=Min('price'))
        return {
            'min': prices['min'],
            'max': prices['max']
        }

    def get_image(self, obj):
        unit = obj.unit_set.filter(unitimage__isnull=False).first()

        # If there are no units for the product:
        if unit is None:
            return None

        # Get image (preferably, main one) for the unit.
        image = unit.unitimage_set.order_by('-is_main').first()

        # If there are no images for the unit:
        if image is None:
            return None

        return image.image.url


# Inherit from list serializer to get tags field.
class ProductSerializer(ProductListSerializer):
    units = UnitSerializer(
        many=True,
        read_only=True,
        source='unit_set'
    )

    class Meta:
        model = Product
        fields = ('id', 'title', 'tags', 'description', 'units')


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ('email', 'password')
        extra_kwargs = {
            'password': {
                'write_only': True
            },
            'email': {
                'validators': [UniqueValidator(queryset=User.objects.all())]
            }
        }

    def create(self, validated_data):
        user = User.objects.create(
            email=validated_data['email'],
            username=validated_data['email']
        )

        user.set_password(validated_data['password'])
        user.save()

        return user


class SellerSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='seller.name')
    address = serializers.CharField(source='seller.address')

    class Meta:
        model = User
        fields = ('email', 'password', 'name', 'address')

    def create(self, validated_data):
        user = User.objects.create(
            email=validated_data['email'],
            username=validated_data['email']
        )

        staff_group = self.get_staff_group()
        user.groups.add(staff_group)

        user.set_password(validated_data['password'])
        user.save()

        Seller.objects.create(
            user=user,
            name=validated_data['seller']['name'],
            address=validated_data['seller']['address']
        )

        return user

    def get_staff_group(self):
        """Get staff group with seller permissions or create if does not exist."""
        try:
            return Group.objects.get(name='Staff')
        except ObjectDoesNotExist:
            group = Group.objects.create(name='Staff')

        all_permissions = ('add', 'change', 'delete')
        content_types = {
            'unit': all_permissions,
            'product': all_permissions,
            'unitimage': all_permissions,
            'orderunit': all_permissions,
            'order': ('change',),
            'property': ('add',),
            'propertyvalue': ('add',)
        }

        for content_type in content_types:
            for permission in content_types[content_type]:
                codename = '{}_{}'.format(permission, content_type)
                permission = Permission.objects.get(codename=codename)
                group.permissions.add(permission)

        return group


class OrderSerializer(serializers.ModelSerializer):

    class Meta:
        model = Order
        fields = ('name', 'address', 'phone')


class OrderListSerializer(serializers.ModelSerializer):
    units_num = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('id', 'created_at', 'units_num')

    def get_units_num(self, obj):
        return obj.unit_set.count()


class UnitForOrderDetail(serializers.ModelSerializer):
    title = serializers.CharField(source='product.title')
    properties = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    product_id = serializers.IntegerField(source='product.id')

    class Meta:
        model = Unit
        fields = ('title', 'properties', 'image', 'product_id', 'price', 'sku')

    def get_properties(self, obj):
        return [{
            'name': property_value.property.name,
            'value': property_value.value
        } for property_value in obj.value_set.all()]

    def get_image(self, obj):
        image = obj.unitimage_set.order_by('-is_main').first()

        if image is None:
            return None

        return image.image.url


class OrderUnitSerializer(serializers.ModelSerializer):
    unit = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = OrderUnit
        fields = ('quantity', 'status', 'unit')

    def get_unit(self, obj):
        data = UnitForOrderDetail(obj.unit).data

        # Use the price that was at the moment of purchase instead of current price.
        data['price'] = obj.unit_price

        return data

    def get_status(self, obj):
        return obj.get_status_display()


class OrderDetailSerializer(serializers.ModelSerializer):
    units = OrderUnitSerializer(
        many=True,
        read_only=True,
        source='orderunit_set'
    )

    class Meta:
        model = Order
        fields = ('id', 'created_at', 'name', 'address', 'phone', 'units')


class CartUnitSerializer(serializers.Serializer):
    sku = serializers.CharField(write_only=True)
    quantity = serializers.IntegerField(default=1, min_value=1)
    unit = UnitForOrderDetail(read_only=True)

    class Meta:
        model = OrderUnit
        fields = ('sku', 'quantity', 'unit')

    def validate(self, data):
        sku = data['sku']
        quantity = data['quantity']

        try:
            unit = Unit.objects.get(sku=sku)
        except ObjectDoesNotExist:
            raise serializers.ValidationError('Unit does not exist')

        if unit.num_in_stock < quantity:
            raise serializers.ValidationError('There are not enough units in stock')

        return data
